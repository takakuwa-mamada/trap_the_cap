// Version: 3.0 - Fixed resetBtn duplicate declaration
const params = new URLSearchParams(window.location.search);
const roomId = params.get('room') || 'test_room';
const playerId = params.get('player') || 'p_' + Math.floor(Math.random() * 1000);

console.log('[Init] Room:', roomId, 'Player:', playerId);
console.log('[Init] Protocol:', window.location.protocol);
console.log('[Init] Host:', window.location.host);

// グローバル変数の宣言（先に宣言）
let gameState = null;
let legalStacks = [];
let legalDirections = [];
let legalDestinations = []; // 移動可能なノード

const canvas = document.getElementById('board');
const ctx = canvas.getContext('2d');
const logDiv = document.getElementById('log');

// UI Elements
const rollBtn = document.getElementById('rollBtn');
const statusDiv = document.getElementById('status');
const directionButtonsDiv = document.getElementById('direction-buttons');
const resetBtn = document.getElementById('resetBtn');

// Settings - 動的に計算
let SCALE = 50;
let OFFSET_X = 300;
let OFFSET_Y = 300;

// Canvas動的リサイズ関数
function resizeCanvas() {
    const container = document.getElementById('game-container');
    const containerWidth = container.clientWidth - 20; // padding分を引く
    const size = Math.min(containerWidth, 600); // 最大600px
    
    canvas.width = size;
    canvas.height = size;
    
    // スケール調整
    SCALE = size / 12; // 12は盤面の基準サイズ
    OFFSET_X = size / 2;
    OFFSET_Y = size / 2;
    
    console.log('[Canvas] Resized:', size, 'SCALE:', SCALE);
    
    // 再描画
    if (gameState) {
        render();
    }
}

// 初回リサイズ＆リサイズイベント登録
resizeCanvas();
window.addEventListener('resize', resizeCanvas);

console.log('[Init] UI elements:', {
    canvas: !!canvas,
    rollBtn: !!rollBtn,
    statusDiv: !!statusDiv,
    directionButtonsDiv: !!directionButtonsDiv
});

// WebSocket接続
const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/${roomId}/${playerId}`;
console.log('[Init] WebSocket URL:', wsUrl);

let ws = null;
let connectionTimeout = null;
let isConnected = false;

function connectWebSocket() {
    console.log('[WS] Attempting connection...');
    statusDiv.textContent = '接続中...';
    
    // 接続タイムアウト（10秒）
    connectionTimeout = setTimeout(() => {
        if (!isConnected) {
            console.error('[WS] Connection timeout');
            statusDiv.textContent = '接続タイムアウト - 再読み込みしてください';
            if (ws) {
                ws.close();
            }
        }
    }, 10000);
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        clearTimeout(connectionTimeout);
        isConnected = true;
        statusDiv.textContent = 'サーバーに接続しました - ゲーム待機中...';
        console.log('[WS] WebSocket connected successfully');
    };
    
    ws.onerror = (error) => {
        console.error('[WS] WebSocket error:', error);
        statusDiv.textContent = '接続エラー - サーバーに接続できません';
    };
    
    ws.onclose = (event) => {
        clearTimeout(connectionTimeout);
        isConnected = false;
        console.log('[WS] WebSocket closed:', event.code, event.reason);
        statusDiv.textContent = '接続が切断されました';
    };
    
    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        console.log('[WS] Received:', message.type || 'state update', message.phase || '');
        
        // Direct state broadcast (GameState object) - 最優先で処理
        if (message.board && !message.type) {
            gameState = message;
            console.log('[WS] Full state update - Phase:', gameState.phase, 'Players:', Object.keys(gameState.players).length);
            // legalStacksはクリアしない（他のメッセージで管理）
            render();
            updateUI();
            return;
        }
        
        if (message.type === 'state_update') {
            gameState = message.payload.game_state;
            console.log('[WS] State update');
            render();
            updateUI();
        } else if (message.type === 'legal_pieces') {
            console.log('[WS] ===== LEGAL PIECES RECEIVED =====');
            console.log('[WS] Stacks:', message.stacks);
            console.log('[WS] Dice:', message.dice_value);
            
            legalStacks = message.stacks || [];
            legalDestinations = []; // リセット
            
            // サイコロの結果を画面に表示
            if (message.dice_value) {
                const diceEmojis = ['⚀', '⚁', '⚂', '⚃', '⚄', '⚅'];
                statusDiv.textContent = `🎲 ${diceEmojis[message.dice_value - 1]} ${message.dice_value}が出ました!`;
                
                if (legalStacks.length === 0) {
                    statusDiv.textContent += ' | 移動できる駒がありません';
                } else {
                    statusDiv.textContent += ` | ${legalStacks.length}個の駒を動かせます（黄色でハイライト）`;
                }
            }
            
            console.log('[WS] Calling render with legalStacks:', legalStacks.length);
            render();
            updateUI();
        } else if (message.type === 'legal_directions') {
            legalDirections = message.directions || [];
            console.log('Legal directions received:', legalDirections);
            updateUI();
        } else if (message.type === 'legal_destinations') {
            console.log('[WS] ===== LEGAL DESTINATIONS RECEIVED =====');
            legalDestinations = message.nodes || [];
            console.log('Legal destinations:', legalDestinations);
            render();
            updateUI();
        }
    };
    
    return ws;
}

// 初回接続
ws = connectWebSocket();

function sendAction(type, payload = {}) {
    ws.send(JSON.stringify({ type, payload }));
}

rollBtn.onclick = () => {
    sendAction("roll");
};

resetBtn.onclick = () => {
    if (confirm('ゲームを最初からやり直しますか?\n全プレイヤーのデータがリセットされます。')) {
        console.log('Reset button clicked');
        sendAction("reset", {});
    }
};

// Direction button handlers
document.querySelectorAll('.dir-btn').forEach(btn => {
    btn.onclick = () => {
        const direction = btn.getAttribute('data-dir');
        console.log('Direction button clicked:', direction);
        sendAction("select_direction", { direction: direction });
        legalDirections = [];
        updateUI();
    };
});

canvas.onclick = (e) => {
    if (!gameState) return;
    
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const clickX = (e.clientX - rect.left) * scaleX;
    const clickY = (e.clientY - rect.top) * scaleY;
    
    handleCanvasClick(clickX, clickY);
};

// タッチイベント対応（スマホ用）
canvas.ontouchstart = (e) => {
    e.preventDefault(); // スクロール防止
    if (!gameState) return;
    
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const touch = e.touches[0];
    const clickX = (touch.clientX - rect.left) * scaleX;
    const clickY = (touch.clientY - rect.top) * scaleY;
    
    handleCanvasClick(clickX, clickY);
};

// クリック/タッチ処理を共通化
function handleCanvasClick(clickX, clickY) {
    // Check if clicking on a legal destination node
    if (legalDestinations.length > 0 && gameState.board && gameState.board.nodes) {
        const nodes = gameState.board.nodes;
        
        // Find which destination was clicked
        for (const nodeId of legalDestinations) {
            const node = nodes[nodeId];
            if (!node) continue;
            
            const {x, y} = toScreen(node.x, node.y);
            const distance = Math.sqrt((clickX - x) ** 2 + (clickY - y) ** 2);
            
            // If clicked within 30px of the destination
            if (distance < 30) {
                console.log('Selecting destination node:', nodeId);
                sendAction("select_destination", { node_id: nodeId });
                legalDestinations = [];
                render();
                return;
            }
        }
    }
    
    // Check if clicking on a legal stack
    if (legalStacks.length > 0 && gameState.board && gameState.board.nodes) {
        const nodes = gameState.board.nodes;
        
        // Find which stack was clicked
        for (const stack of legalStacks) {
            const node = nodes[stack.node_id];
            if (!node) continue;
            
            const {x, y} = toScreen(node.x, node.y);
            const distance = Math.sqrt((clickX - x) ** 2 + (clickY - y) ** 2);
            
            // If clicked within 30px of the stack
            if (distance < 30) {
                console.log('Selecting piece at node:', stack.node_id);
                sendAction("select_piece", { stack: stack });
                legalStacks = [];
                render();
                return;
            }
        }
    }
}

function updateUI() {
    if (!gameState) return;
    
    // Status
    const currentPlayerId = gameState.turn_order ? gameState.turn_order[gameState.current_turn_index] : null;
    const isMyTurn = currentPlayerId === playerId;
    
    const phaseNames = {
        'ROLL': 'サイコロを振る',
        'SELECT_PIECE': '駒を選択',
        'SELECT_DIRECTION': '方向を選択',
        'GAME_OVER': 'ゲーム終了'
    };
    
    let statusText = `${phaseNames[gameState.phase] || gameState.phase} | 部屋: ${gameState.room_id}`;
    if (currentPlayerId) {
        const currentPlayer = gameState.players[currentPlayerId];
        statusText += ` | 手番: ${currentPlayer?.name || currentPlayerId} ${isMyTurn ? '(あなた)' : ''}`;
    }
    statusDiv.textContent = statusText;
    
    // Roll button
    if (isMyTurn && gameState.phase === "ROLL") {
        rollBtn.disabled = false;
        rollBtn.textContent = "🎲 サイコロを振る";
    } else {
        rollBtn.disabled = true;
        if (gameState.dice_value) {
            rollBtn.textContent = `🎲 出た目: ${gameState.dice_value}`;
        } else {
            rollBtn.textContent = "🎲 サイコロを振る";
        }
    }
    
    // Direction buttons
    if (legalDirections.length > 0 && isMyTurn) {
        directionButtonsDiv.style.display = 'flex';
        // Show only available directions
        document.querySelectorAll('.dir-btn').forEach(btn => {
            const dir = btn.getAttribute('data-dir');
            if (legalDirections.includes(dir)) {
                btn.style.display = 'inline-block';
            } else {
                btn.style.display = 'none';
            }
        });
    } else {
        directionButtonsDiv.style.display = 'none';
    }

    // Logs
    if (gameState.logs && gameState.logs.length > 0) {
        logDiv.innerHTML = gameState.logs.slice(-10).map(l => 
            `<div><b>[${l.player_id}]</b> ${l.action_type}: ${JSON.stringify(l.details).substring(0, 50)}</div>`
        ).join('');
    }
    
    // Players info
    const playersInfoDiv = document.getElementById('players-info');
    if (gameState.players && playersInfoDiv) {
        const colorMap = {
            'RED': '#E74C3C',
            'BLUE': '#3498DB',
            'YELLOW': '#F1C40F',
            'GREEN': '#2ECC71'
        };
        
        playersInfoDiv.innerHTML = Object.entries(gameState.players).map(([pid, player]) => {
            const boxCount = player.box_hats ? player.box_hats.length : 0;
            const bankedCount = player.banked_hats ? player.banked_hats.length : 0;
            // ポイント計算：敵の駒のみカウント
            const points = player.banked_hats ? 
                player.banked_hats.filter(h => h.color !== player.color).length : 0;
            const isYou = pid === playerId ? ' (あなた)' : '';
            const isBot = player.is_bot ? ' [コンピュータ]' : '';
            const color = colorMap[player.color] || '#888';
            
            return `<div style="border-left-color: ${color}">
                🎩 <b>${player.name}${isYou}${isBot}</b>: BOX内=${boxCount}個 | ポイント=<b>${points}</b>点
            </div>`;
        }).join('');
    }
    
    // Instructions
    if (isMyTurn) {
        if (gameState.phase === "ROLL") {
            statusDiv.textContent += ' | 🎲 ボタンをクリックしてサイコロを振ってください';
        } else if (legalStacks.length > 0) {
            statusDiv.textContent += ' | 📍 黄色く光っている駒をクリックしてください';
        } else if (legalDestinations.length > 0) {
            statusDiv.textContent += ' | 🎯 緑色で光っているマスをクリックして移動先を選んでください';
        } else if (legalDirections.length > 0) {
            statusDiv.textContent += ' | ➡️ 移動する方向を選んでください';
        }
    }
}

function toScreen(nx, ny) {
    return {
        x: nx * SCALE + OFFSET_X,
        y: ny * SCALE + OFFSET_Y
    };
}

function render() {
    if (!gameState) return;
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Background - bright sky blue
    ctx.fillStyle = '#5DB8E5';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Draw board structure
    if (!gameState.board || !gameState.board.nodes) return;
    
    let nodes = gameState.board.nodes;
    
    // nodesが配列の場合、オブジェクトに変換
    if (Array.isArray(nodes)) {
        const nodesObj = {};
        nodes.forEach(node => {
            if (node && node.id) {
                nodesObj[node.id] = node;
            }
        });
        nodes = nodesObj;
    }
    
    if (!nodes || Object.keys(nodes).length === 0) {
        console.error('[Render] No valid nodes found');
        return;
    }
    
    const centerX = OFFSET_X;
    const centerY = OFFSET_Y;
    
    // === STEP 1: Draw outer ring (thick beige band) ===
    const ringRadius = 3.0 * SCALE;  // Radius to center of ring
    const ringWidth = 0.6 * SCALE;   // Thickness of ring band
    
    ctx.fillStyle = '#D4A574';  // Beige
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 5;
    
    // Outer circle
    ctx.beginPath();
    ctx.arc(centerX, centerY, ringRadius + ringWidth/2, 0, Math.PI * 2);
    ctx.stroke();
    
    // Inner circle
    ctx.beginPath();
    ctx.arc(centerX, centerY, ringRadius - ringWidth/2, 0, Math.PI * 2);
    ctx.stroke();
    
    // Fill ring area
    ctx.beginPath();
    ctx.arc(centerX, centerY, ringRadius + ringWidth/2, 0, Math.PI * 2);
    ctx.arc(centerX, centerY, ringRadius - ringWidth/2, 0, Math.PI * 2, true);
    ctx.fill();
    
    // === STEP 2: Draw X-cross paths (4 beige bands) ===
    const crossPaths = [
        { startAngle: -Math.PI/4, endAngle: Math.PI/4 },       // East
        { startAngle: Math.PI/4, endAngle: 3*Math.PI/4 },      // South
        { startAngle: 3*Math.PI/4, endAngle: 5*Math.PI/4 },    // West
        { startAngle: 5*Math.PI/4, endAngle: 7*Math.PI/4 }     // North
    ];
    
    const crossWidth = 0.6 * SCALE;  // Width of cross paths
    const innerRadius = ringRadius - ringWidth/2;
    
    crossPaths.forEach((path, idx) => {
        const midAngle = (path.startAngle + path.endAngle) / 2;
        const cos = Math.cos(midAngle);
        const sin = Math.sin(midAngle);
        const perpCos = Math.cos(midAngle + Math.PI/2);
        const perpSin = Math.sin(midAngle + Math.PI/2);
        
        // Draw beige band from center to inner ring
        ctx.fillStyle = '#D4A574';
        ctx.beginPath();
        ctx.moveTo(centerX + perpCos * crossWidth/2, centerY + perpSin * crossWidth/2);
        ctx.lineTo(centerX + cos * innerRadius + perpCos * crossWidth/2, 
                   centerY + sin * innerRadius + perpSin * crossWidth/2);
        ctx.lineTo(centerX + cos * innerRadius - perpCos * crossWidth/2,
                   centerY + sin * innerRadius - perpSin * crossWidth/2);
        ctx.lineTo(centerX - perpCos * crossWidth/2, centerY - perpSin * crossWidth/2);
        ctx.closePath();
        ctx.fill();
        
        // Draw black outline edges
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(centerX + perpCos * crossWidth/2, centerY + perpSin * crossWidth/2);
        ctx.lineTo(centerX + cos * innerRadius + perpCos * crossWidth/2,
                   centerY + sin * innerRadius + perpSin * crossWidth/2);
        ctx.stroke();
        
        ctx.beginPath();
        ctx.moveTo(centerX - perpCos * crossWidth/2, centerY - perpSin * crossWidth/2);
        ctx.lineTo(centerX + cos * innerRadius - perpCos * crossWidth/2,
                   centerY + sin * innerRadius - perpSin * crossWidth/2);
        ctx.stroke();
    });
    
    // === STEP 3: Draw central blue circle ===
    ctx.fillStyle = '#5DB8E5';
    ctx.beginPath();
    ctx.arc(centerX, centerY, 0.8 * SCALE, 0, Math.PI * 2);
    ctx.fill();
    
    // === STEP 4: Draw division lines on outer ring ===
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 2.5;
    for (let i = 0; i < 48; i++) {
        const angle = (i / 48) * Math.PI * 2 - Math.PI / 2;  // Start from top
        const x1 = centerX + Math.cos(angle) * (ringRadius - ringWidth/2);
        const y1 = centerY + Math.sin(angle) * (ringRadius - ringWidth/2);
        const x2 = centerX + Math.cos(angle) * (ringRadius + ringWidth/2);
        const y2 = centerY + Math.sin(angle) * (ringRadius + ringWidth/2);
        
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
    }
    
    // === STEP 5: Draw division lines on cross paths ===
    const crossDivLineLength = crossWidth / 2 + 5;
    
    // North cross (vertical)
    for (let i = 1; i <= 2; i++) {
        const y = centerY - i * (innerRadius / 3);
        ctx.beginPath();
        ctx.moveTo(centerX - crossDivLineLength, y);
        ctx.lineTo(centerX + crossDivLineLength, y);
        ctx.stroke();
    }
    
    // South cross (vertical)
    for (let i = 1; i <= 2; i++) {
        const y = centerY + i * (innerRadius / 3);
        ctx.beginPath();
        ctx.moveTo(centerX - crossDivLineLength, y);
        ctx.lineTo(centerX + crossDivLineLength, y);
        ctx.stroke();
    }
    
    // East cross (horizontal)
    for (let i = 1; i <= 2; i++) {
        const x = centerX + i * (innerRadius / 3);
        ctx.beginPath();
        ctx.moveTo(x, centerY - crossDivLineLength);
        ctx.lineTo(x, centerY + crossDivLineLength);
        ctx.stroke();
    }
    
    // West cross (horizontal)
    for (let i = 1; i <= 2; i++) {
        const x = centerX - i * (innerRadius / 3);
        ctx.beginPath();
        ctx.moveTo(x, centerY - crossDivLineLength);
        ctx.lineTo(x, centerY + crossDivLineLength);
        ctx.stroke();
    }
    
    // Define colors
    const colorMap = {
        'RED': '#D32F2F',
        'BLUE': '#1976D2',
        'YELLOW': '#FDD835',
        'GREEN': '#388E3C'
    };
    
    // === STEP 6: Draw small dots at each node position (for debugging alignment) ===
    Object.entries(nodes).forEach(([nodeId, node]) => {
        if (!node.tags) return;
        if (node.tags.includes('BOX')) return;  // Skip BOX
        if (node.tags.includes('CENTER')) return;  // Skip center
        
        const {x, y} = toScreen(node.x, node.y);
        
        if (node.tags.includes('SAFE_COLOR')) {
            // Colored squares - exact node position
            ctx.fillStyle = colorMap[node.color] || '#888';
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 2.5;
            const size = 20;
            
            ctx.fillRect(x - size/2, y - size/2, size, size);
            ctx.strokeRect(x - size/2, y - size/2, size, size);
        } else {
            // Draw small circle at node position to show exact location
            ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
            ctx.beginPath();
            ctx.arc(x, y, 3, 0, Math.PI * 2);
            ctx.fill();
        }
    });
    
    // === STEP 7: Draw BOX circles with arrows ===
    Object.entries(nodes).forEach(([nodeId, node]) => {
        if (!node.tags || !node.tags.includes('BOX')) return;
        
        const {x, y} = toScreen(node.x, node.y);
        
        ctx.save();
        
        // White outer glow
        ctx.fillStyle = '#fff';
        ctx.shadowColor = 'rgba(255,255,255,0.9)';
        ctx.shadowBlur = 20;
        ctx.beginPath();
        ctx.arc(x, y, 48, 0, Math.PI*2);
        ctx.fill();
        ctx.shadowBlur = 0;
        
        // Colored BOX
        ctx.fillStyle = colorMap[node.color] || '#444';
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 6;
        ctx.beginPath();
        ctx.arc(x, y, 40, 0, Math.PI*2);
        ctx.fill();
        ctx.stroke();
        
        // BOX label
        ctx.fillStyle = '#fff';
        ctx.strokeStyle = 'rgba(0,0,0,0.5)';
        ctx.lineWidth = 3;
        ctx.font = 'bold 20px Arial';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.strokeText('BOX', x, y);
        ctx.fillText('BOX', x, y);
        
        ctx.restore();
        
        // Arrow toward center
        ctx.save();
        ctx.strokeStyle = '#000';
        ctx.fillStyle = '#000';
        ctx.lineWidth = 5;
        const arrowAngle = Math.atan2(centerY - y, centerX - x);
        const arrowStartDist = 45;
        const arrowEndDist = 70;
        const arrowStartX = x + Math.cos(arrowAngle) * arrowStartDist;
        const arrowStartY = y + Math.sin(arrowAngle) * arrowStartDist;
        const arrowEndX = x + Math.cos(arrowAngle) * arrowEndDist;
        const arrowEndY = y + Math.sin(arrowAngle) * arrowEndDist;
        
        ctx.beginPath();
        ctx.moveTo(arrowStartX, arrowStartY);
        ctx.lineTo(arrowEndX, arrowEndY);
        ctx.stroke();
        
        const headLen = 14;
        ctx.beginPath();
        ctx.moveTo(arrowEndX, arrowEndY);
        ctx.lineTo(arrowEndX - headLen * Math.cos(arrowAngle - Math.PI/6),
                  arrowEndY - headLen * Math.sin(arrowAngle - Math.PI/6));
        ctx.lineTo(arrowEndX - headLen * Math.cos(arrowAngle + Math.PI/6),
                  arrowEndY - headLen * Math.sin(arrowAngle + Math.PI/6));
        ctx.closePath();
        ctx.fill();
        ctx.restore();
    });
    
    // Draw stacks (hats on board)
    if (gameState.stacks) {
        gameState.stacks.forEach(stack => {
            const node = nodes[stack.node_id];
            if (!node) return;
            
            const {x, y} = toScreen(node.x, node.y);
            
            // Define colors for hats - match board colors
            const colorMap = {
                'RED': '#D32F2F',
                'BLUE': '#1976D2',
                'YELLOW': '#FDD835',
                'GREEN': '#388E3C'
            };
            
            // Draw stack pieces (hats) - 駒を下から順に積み重ねて表示
            // pieces[0]=底（先にいた駒）、pieces[last]=天辺（後から来た駒）
            stack.pieces.forEach((piece, idx) => {
                // デバッグ: スタックの内容を表示
                if (stack.pieces.length > 1 && idx === 0) {
                    console.log(`[Render] Stack at ${stack.node_id}:`, 
                        stack.pieces.map((p, i) => `${i}:${p.color}(${p.id})`).join(' < '),
                        `(${stack.pieces.length} pieces, ${stack.pieces[0].id} at bottom, ${stack.pieces[stack.pieces.length-1].id} at top)`);
                }
                
                // 駒を斜め右上方向に重ねる（全ての駒が見えるように）
                // idx=0が底（左下）、idx=lastが天辺（右上）
                const stackHeight = stack.pieces.length;
                const yOffset = -idx * 12;  // 上に12pxずつずらす
                const xOffset = idx * 12;   // 右に12pxずつずらして全ての駒を見せる
                
                // 影を追加して立体感を出す（より濃く）
                ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
                ctx.beginPath();
                ctx.arc(x + xOffset + 2, y + yOffset + 2, 12, 0, Math.PI*2);
                ctx.fill();
                
                // Draw hat shape (circle) - 駒本体
                ctx.fillStyle = colorMap[piece.color] || '#888';
                ctx.strokeStyle = '#000';
                ctx.lineWidth = 2.5;
                ctx.beginPath();
                ctx.arc(x + xOffset, y + yOffset, 12, 0, Math.PI*2);
                ctx.fill();
                ctx.stroke();
                
                // Add hat "brim" (white line on top) - 駒の上部を強調
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2.5;
                ctx.beginPath();
                ctx.arc(x + xOffset, y + yOffset, 12, -Math.PI * 0.8, -Math.PI * 0.2);
                ctx.stroke();
                
                // 各駒に色付き光彩を追加（重なりをより明確に）
                ctx.strokeStyle = colorMap[piece.color];
                ctx.lineWidth = 2;
                ctx.globalAlpha = 0.6;
                ctx.beginPath();
                ctx.arc(x + xOffset, y + yOffset, 15, 0, Math.PI*2);
                ctx.stroke();
                ctx.globalAlpha = 1.0;
                
                // 駒のIDを小さく表示（デバッグ用）
                if (stackHeight > 1) {
                    ctx.fillStyle = '#fff';
                    ctx.strokeStyle = '#000';
                    ctx.lineWidth = 2;
                    ctx.font = 'bold 8px Arial';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.strokeText(piece.id.split('_')[1], x + xOffset, y + yOffset);
                    ctx.fillText(piece.id.split('_')[1], x + xOffset, y + yOffset);
                }
            });
            
            // スタック情報を表示（重なっている駒の数）
            if (stack.pieces.length > 1) {
                const topX = x + (stack.pieces.length - 1) * 12 + 18;
                const topY = y - (stack.pieces.length - 1) * 12;
                
                // 駒の数を表示（白い縁取り付き）
                ctx.fillStyle = '#FF0000';
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 3;
                ctx.font = 'bold 14px Arial';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.strokeText('×' + stack.pieces.length, topX, topY);
                ctx.fillText('×' + stack.pieces.length, topX, topY);
            }
        });
    }
    
    // Player info is now shown in the status div, not on canvas
    
    // Highlight legal stacks
    if (legalStacks.length > 0) {
        ctx.strokeStyle = '#FFD700';
        ctx.lineWidth = 5;
        legalStacks.forEach(stack => {
            const node = nodes[stack.node_id];
            if (!node) return;
            const {x, y} = toScreen(node.x, node.y);
            ctx.beginPath();
            ctx.arc(x, y, 25, 0, Math.PI*2);
            ctx.stroke();
        });
    }
    
    // Highlight legal destination nodes
    if (legalDestinations.length > 0) {
        ctx.strokeStyle = '#00FF00'; // 緑色
        ctx.lineWidth = 5;
        legalDestinations.forEach(nodeId => {
            const node = nodes[nodeId];
            if (!node) {
                console.warn('[Render] Legal destination node not found:', nodeId);
                return;
            }
            const {x, y} = toScreen(node.x, node.y);
            
            // BOXノードの場合は大きな円を描画
            const radius = node.tags && node.tags.includes('BOX') ? 40 : 25;
            
            ctx.beginPath();
            ctx.arc(x, y, radius, 0, Math.PI*2);
            ctx.stroke();
            
            // 中心に印をつける
            ctx.fillStyle = '#00FF00';
            ctx.beginPath();
            ctx.arc(x, y, 5, 0, Math.PI*2);
            ctx.fill();
        });
    }
}

// Initial render
render();
