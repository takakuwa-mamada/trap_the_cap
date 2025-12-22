const params = new URLSearchParams(window.location.search);
const roomId = params.get('room') || 'test_room';
const playerId = params.get('player') || 'p_' + Math.floor(Math.random() * 1000);

const ws = new WebSocket(`${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/${roomId}/${playerId}`);

let gameState = null;
const canvas = document.getElementById('board');
const ctx = canvas.getContext('2d');
const logDiv = document.getElementById('log');

// UI Elements
const rollBtn = document.getElementById('rollBtn');
const statusDiv = document.getElementById('status');

// Settings
const SCALE = 30;
const OFFSET_X = 300;
const OFFSET_Y = 300;

ws.onmessage = (event) => {
    gameState = JSON.parse(event.data);
    render();
    updateUI();
};

function sendAction(type, payload = {}) {
    ws.send(JSON.stringify({ type, payload }));
}

rollBtn.onclick = () => sendAction("ROLL");

function updateUI() {
    if (!gameState) return;
    
    // Status
    const isMyTurn = gameState.turn_order[gameState.current_turn_index] === playerId;
    statusDiv.textContent = `Phase: ${gameState.phase} | Turn: ${gameState.current_player_id} ${isMyTurn ? "(YOU)" : ""}`;
    
    if (isMyTurn && gameState.phase === "ROLL") {
        rollBtn.disabled = false;
        rollBtn.textContent = "ROLL DICE";
    } else {
        rollBtn.disabled = true;
        if (gameState.dice_value) {
            rollBtn.textContent = `Dice: ${gameState.dice_value}`;
        }
    }

    // Logs
    logDiv.innerHTML = gameState.logs.slice(-5).map(l => 
        `<div>[${l.player_id}] ${l.action_type} ${JSON.stringify(l.details)}</div>`
    ).join('');
}

function render() {
    if (!gameState) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Nodes & Edges
    // Edges
    ctx.strokeStyle = '#aaa';
    ctx.lineWidth = 2;
    Object.values(gameState.nodes).forEach(node => {
        const {x, y} = toScreen(node.x, node.y);
        node.neighbors.forEach(nid => {
            const neighbor = gameState.nodes[nid];
            const {x: nx, y: ny} = toScreen(neighbor.x, neighbor.y);
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.lineTo(nx, ny);
            ctx.stroke();
        });
    });

    // Nodes
    Object.values(gameState.nodes).forEach(node => {
        const {x, y} = toScreen(node.x, node.y);
        ctx.beginPath();
        ctx.arc(x, y, 10, 0, Math.PI*2);
        ctx.fillStyle = getColor(node);
        ctx.fill();
        ctx.stroke();
        
        // Tags
        if (node.tags.includes("SAFE")) {
            ctx.strokeStyle = "gold";
            ctx.lineWidth = 3;
            ctx.stroke();
            ctx.strokeStyle = "black";
            ctx.lineWidth = 1;
        }
    });

    // Stacks
    Object.values(gameState.stacks).forEach(stack => {
        const node = gameState.nodes[stack.node_id];
        const {x, y} = toScreen(node.x, node.y);
        
        // Stack rendering (simple circle stack)
        const count = stack.pieces.length;
        const topColor = stack.pieces[count-1].color;
        
        ctx.beginPath();
        ctx.arc(x, y - 5, 12, 0, Math.PI*2);
        ctx.fillStyle = topColor.toLowerCase();
        ctx.fill();
        ctx.stroke();
        
        ctx.fillStyle = "white";
        ctx.font = "12px Arial";
        ctx.fillText(count, x-3, y);
    });
    
    // Highlight Legal Moves Target Nodes
    if (gameState.phase === "SELECT" && gameState.current_player_id === playerId) {
        gameState.legal_moves.forEach(move => {
            const targetId = move.path[move.path.length - 1];
            const node = gameState.nodes[targetId];
            const {x, y} = toScreen(node.x, node.y);
            
            ctx.beginPath();
            ctx.arc(x, y, 15, 0, Math.PI*2);
            ctx.strokeStyle = "cyan";
            ctx.lineWidth = 3;
            ctx.stroke();
        });
    }
}

function toScreen(gx, gy) {
    return { x: OFFSET_X + gx * SCALE, y: OFFSET_Y + gy * SCALE };
}

function getColor(node) {
    if (node.home_color) return node.home_color.toLowerCase();
    if (node.tags.includes("SAFE")) return "#eee";
    return "#fff";
}

// Click Handling for Move Selection
canvas.addEventListener('click', (e) => {
    if (!gameState || gameState.phase !== "SELECT" || gameState.current_player_id !== playerId) return;
    
    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    
    // Check if clicked near a valid move target
    for (const move of gameState.legal_moves) {
        const targetId = move.path[move.path.length - 1];
        const node = gameState.nodes[targetId];
        const {x, y} = toScreen(node.x, node.y);
        
        const dist = Math.hypot(clickX - x, clickY - y);
        if (dist < 20) {
            sendAction("MOVE", { move_id: move.move_id });
            return;
        }
    }
});