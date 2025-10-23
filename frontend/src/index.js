function initCharts() {
    console.log('initCharts initialized');
}

function loadExternalContent(file, targetId) {
    const targetElement = document.getElementById(targetId);

    targetElement.innerHTML = `
        <div class="external-tab-header">
            <div class="external-tab-actions"></div>
        </div>
        <div class="loading-spinner d-flex align-items-center">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Загрузка...</span>
            </div>
            <span class="ms-3">Загрузка ${file}...</span>
        </div>
    `;

    setTimeout(() => {
        targetElement.innerHTML = `
            <iframe src="${file}" style="width:100%; height:calc(100% - 60px); border:none;"></iframe>
        `;
    }, 500);
}

function refreshExternalContent(file, targetId) {
    loadExternalContent(file, targetId);
}

function openInNewTab(url) {
    window.open(url, '_blank');
}

document.addEventListener('DOMContentLoaded', function() {
    const mainTab = document.getElementById('main-tab');
    const cardTab = document.getElementById('card-tab');
    
    mainTab.addEventListener('click', function() {
        const mainContent = document.getElementById('main-content');
        if (!mainContent.querySelector('iframe')) {
            loadExternalContent('main.html', 'main-content');
        }
    });
    
    cardTab.addEventListener('click', function() {
        const cardContent = document.getElementById('card-content');
        if (!cardContent.querySelector('iframe')) {
            loadExternalContent('card.html', 'card-content');
        }
    });

    const scenarioControls = document.getElementById('scenario-controls');
    const stopBtn = document.getElementById('stopScenarioBtn');
    const resumeBtn = document.getElementById('resumeScenarioBtn');
    let scenarioActive = false;

    function updateScenarioButtons() {
        if (scenarioActive) {
            resumeBtn.classList.remove('active');
            stopBtn.classList.add('active');
        } else {
            stopBtn.classList.remove('active');
            resumeBtn.classList.add('active');
        }
    }
    
    if (stopBtn && resumeBtn) {
        stopBtn.onclick = function() {
            scenarioActive = false;
            updateScenarioButtons();
            if (window.websocket && window.websocket.readyState === WebSocket.OPEN) {
                window.websocket.send(JSON.stringify({ action: 'stop_lua' }));
            }
        };
        resumeBtn.onclick = function() {
            scenarioActive = true;
            updateScenarioButtons();
            if (window.websocket && window.websocket.readyState === WebSocket.OPEN) {
                window.websocket.send(JSON.stringify({ action: 'run_lua', script: 'main.lua' }));
            }
        };
        updateScenarioButtons();
    }

    document.getElementById('myTab').addEventListener('click', function(e) {
        setTimeout(() => {
            const activeTab = document.querySelector('.nav-link.active');
            if (activeTab && activeTab.id === 'tests-tab') {
                scenarioControls.style.display = '';
            } else {
                scenarioControls.style.display = 'none';
            }
        }, 10);
    });
});