const rpmHeaders = [800, 900, 1000, 1500, 2000, 2500, 3000, 4000, 4500, 5000, 5500, 6000, 6500, 7000, 7500, 8000];
const mapValues = [425, 400, 375, 350, 325];

const sparkAngleData = [];
for (let i = 0; i < mapValues.length; i++) {
    const row = [mapValues[i]];
    for (let j = 0; j < rpmHeaders.length; j++) {
        row.push(Math.floor(Math.random() * 21) + 20);
    }
    sparkAngleData.push(row);
}

const delayData = [];
for (let i = 0; i < mapValues.length; i++) {
    const row = [mapValues[i]];
    for (let j = 0; j < rpmHeaders.length; j++) {
        row.push(Math.floor(Math.random() * 14001) + 1000);
    }
    delayData.push(row);
}

let currentRPM = 3000;
let currentMAP = 375;
let currentPoint = null;

function getSparkAngleClass(value) {
    if (value <= 25) return 'spark-low';
    if (value <= 35) return 'spark-medium';
    return 'spark-high';
}

function getDelayClass(value) {
    if (value <= 5000) return 'delay-low';
    if (value <= 10000) return 'delay-medium';
    return 'delay-high';
}

function findClosestIndex(arr, value) {
    return arr.reduce((closest, current, index) => {
        return Math.abs(current - value) < Math.abs(arr[closest] - value) ? index : closest;
    }, 0);
}

function updateCurrentPoint() {
    const rpmIndex = findClosestIndex(rpmHeaders, currentRPM);
    const mapIndex = findClosestIndex(mapValues, currentMAP);
    
    const angleValue = sparkAngleData[mapIndex][rpmIndex + 1];
    const delayValue = delayData[mapIndex][rpmIndex + 1];
    
    document.getElementById('status-rpm').textContent = currentRPM;
    document.getElementById('status-map').textContent = currentMAP;
    document.getElementById('status-angle').textContent = angleValue;
    document.getElementById('status-delay').textContent = delayValue;
    
    highlightTableCells('spark-angle-table', mapIndex, rpmIndex);
    highlightTableCells('delay-table', mapIndex, rpmIndex);
    
    update3DPoint(mapIndex, rpmIndex, angleValue);
}

function highlightTableCells(tableId, mapIndex, rpmIndex) {
    const table = document.getElementById(tableId);
    const cells = table.querySelectorAll('td.current-point');
    cells.forEach(cell => cell.classList.remove('current-point'));
    
    const row = table.rows[mapIndex + 1];
    if (row) {
        const cell = row.cells[rpmIndex + 1];
        if (cell) {
            cell.classList.add('current-point');
            cell.scrollIntoView({block: 'nearest', inline: 'nearest'});
        }
    }
}

function update3DPoint(mapIndex, rpmIndex, angleValue) {
    if (currentPoint) {
        scene.remove(currentPoint);
        currentPoint.geometry.dispose();
        currentPoint.material.dispose();
    }
    
    const segments = 50;
    const size = 10;
    const x = (rpmIndex / (rpmHeaders.length - 1) - 0.5) * size;
    const y = (mapIndex / (mapValues.length - 1) - 0.5) * size;
    
    const z = funcMap[currentFunction](x, y) * heightScale;
    
    const geometry = new THREE.SphereGeometry(0.3, 16, 16);
    const material = new THREE.MeshBasicMaterial({ color: 0xFFFFFF });
    currentPoint = new THREE.Mesh(geometry, material);
    currentPoint.position.set(x, z, y);
    
    scene.add(currentPoint);
}

function createTable(tableId, headers, data, tableType) {
    const table = document.getElementById(tableId);
    table.innerHTML = '';
    
    const headerRow = document.createElement('tr');
    headerRow.className = 'table-header-row';
    
    const emptyHeader = document.createElement('th');
    emptyHeader.textContent = 'RPM';
    headerRow.appendChild(emptyHeader);
    
    headers.forEach(rpm => {
        const th = document.createElement('th');
        th.textContent = rpm;
        th.className = 'table-header-cell';
        headerRow.appendChild(th);
    });
    
    table.appendChild(headerRow);
    
    data.forEach((rowData, rowIndex) => {
        const row = document.createElement('tr');
        
        const mapCell = document.createElement('td');
        mapCell.textContent = rowData[0];
        mapCell.className = 'map-values';
        row.appendChild(mapCell);
        
        for (let i = 1; i < rowData.length; i++) {
            const cell = document.createElement('td');
            cell.textContent = rowData[i];
            
            if (tableType === 'spark') {
                cell.classList.add(getSparkAngleClass(rowData[i]));
            } else if (tableType === 'delay') {
                cell.classList.add(getDelayClass(rowData[i]));
            }
            
            cell.setAttribute('data-rpm-index', i - 1);
            cell.setAttribute('data-map-index', rowIndex);
            
            row.appendChild(cell);
        }
        
        table.appendChild(row);
    });
}

let scene, camera, renderer, controls, terrain;
let heightScale = 1;
let rotationSpeed = 0;
let currentFunction = 'sincos';
let wireframeVisible = false;

function initThreeJS() {
    const container = document.getElementById('terrain-container');
    const width = container.clientWidth;
    const height = container.clientHeight;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1a2a3a);

    camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
    camera.position.set(50, 50, 50);
    camera.lookAt(0, 0, 0);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    container.appendChild(renderer.domElement);

    const ambientLight = new THREE.AmbientLight(0x404040);
    scene.add(ambientLight);

    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(1, 1, 1);
    scene.add(directionalLight);

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;

    createFunctionTerrain();

    window.addEventListener('resize', () => {
        const width = container.clientWidth;
        const height = container.clientHeight;

        camera.aspect = width / height;
        camera.updateProjectionMatrix();

        renderer.setSize(width, height);
    });

    updateCurrentPoint();
    
    animate();
}

function createFunctionTerrain() {
    if (terrain) {
        scene.remove(terrain);
        terrain.geometry.dispose();
        terrain.material.dispose();
        terrain = null;
    }

    const segments = 50;
    const size = 10;
    const geometry = new THREE.PlaneGeometry(size, size, segments, segments);

    const vertices = geometry.attributes.position.array;
    const colors = [];
    const color = new THREE.Color();

    for (let i = 0; i < vertices.length; i += 3) {
        const x = vertices[i];
        const y = vertices[i + 1];
        
        let z;
        switch(currentFunction) {
            case 'sincos':
                z = z = interp2D(x, y, segments, size, funcMap[currentFunction]);
                break;
            case 'sin':
                z = Math.sin(x);
                break;
            case 'cos':
                z = Math.cos(x);
                break;
            default:
                z = z = interp2D(x, y, segments, size, funcMap[currentFunction]);
        }
        
        vertices[i + 2] = z * 1 * heightScale;

        const normalizedValue = (z + 1) / 2;
        
        if(normalizedValue < 0.5) {
            color.setRGB(2 * normalizedValue, 1, 0);
        } else {
            color.setRGB(1, 2 * (1 - normalizedValue), 0);
        }
        colors.push(color.r, color.g, color.b);
    }

    geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    geometry.computeVertexNormals();

    const material = new THREE.MeshPhongMaterial({
        vertexColors: true,
        wireframe: wireframeVisible,
        side: THREE.DoubleSide,
        flatShading: true
    });

    terrain = new THREE.Mesh(geometry, material);
    terrain.rotation.x = -Math.PI / 2;
    scene.add(terrain);
}

function animate() {
    requestAnimationFrame(animate);

    if (rotationSpeed > 0 && terrain) {
        terrain.rotation.y += rotationSpeed / 1000;
    }

    controls.update();
    renderer.render(scene, camera);
}

function interp2D(x, y, segments, size, func) {
    const step = size / segments;
    const halfSize = size / 2;

    const x0 = Math.floor((x + halfSize) / step);
    const y0 = Math.floor((y + halfSize) / step);
    const x1 = x0 + 1;
    const y1 = y0 + 1;

    if (x0 < 0 || y0 < 0 || x1 > segments || y1 > segments) return 0;

    const x0Pos = x0 * step - halfSize;
    const y0Pos = y0 * step - halfSize;
    const x1Pos = x1 * step - halfSize;
    const y1Pos = y1 * step - halfSize;

    const Q11 = func(x0Pos, y0Pos);
    const Q21 = func(x1Pos, y0Pos);
    const Q12 = func(x0Pos, y1Pos);
    const Q22 = func(x1Pos, y1Pos);

    const R1 = ((x1Pos - x) / (x1Pos - x0Pos)) * Q11 + ((x - x0Pos) / (x1Pos - x0Pos)) * Q21;
    const R2 = ((x1Pos - x) / (x1Pos - x0Pos)) * Q12 + ((x - x0Pos) / (x1Pos - x0Pos)) * Q22;

    const P = ((y1Pos - y) / (y1Pos - y0Pos)) * R1 + ((y - y0Pos) / (y1Pos - y0Pos)) * R2;

    return P;
}

document.getElementById('go-card').addEventListener('click', () => {
    window.location.href = 'card.html';
});

const funcMap = {
    sincos: (x, y) => Math.sin(x) * Math.cos(y),
    sin: (x, y) => Math.sin(x),
    cos: (x, y) => Math.cos(x)
};

function initControls() {
    document.getElementById('reset-view').addEventListener('click', () => {
        controls.reset();
        camera.position.set(50, 50, 50);
        camera.lookAt(0, 0, 0);
    });

    document.getElementById('toggle-wireframe').addEventListener('click', () => {
        wireframeVisible = !wireframeVisible;
        terrain.material.wireframe = wireframeVisible;
    });

    document.getElementById('change-color').addEventListener('click', () => {
        const colors = [0x3498db, 0xe74c3c, 0x2ecc71, 0xf39c12, 0x9b59b6];
        const randomColor = colors[Math.floor(Math.random() * colors.length)];
        terrain.material.color.setHex(randomColor);
    });

    document.getElementById('rpm-slider').addEventListener('input', (e) => {
        currentRPM = parseInt(e.target.value);
        document.getElementById('current-rpm').textContent = currentRPM;
        updateCurrentPoint();
    });

    document.getElementById('map-slider').addEventListener('input', (e) => {
        currentMAP = parseInt(e.target.value);
        document.getElementById('current-map').textContent = currentMAP;
        updateCurrentPoint();
    });

    document.querySelectorAll('[data-param]').forEach(button => {
        button.addEventListener('click', () => {
            currentFunction = button.getAttribute('data-param');
            createFunctionTerrain();
            updateCurrentPoint();
        });
    });
}

window.addEventListener('load', () => {
    createTable('spark-angle-table', rpmHeaders, sparkAngleData, 'spark');
    createTable('delay-table', rpmHeaders, delayData, 'delay');
    
    initThreeJS();
    initControls();
});