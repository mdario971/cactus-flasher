// Cactus Flasher - Frontend Application

class CactusFlasher {
    constructor() {
        this.token = localStorage.getItem('token');
        this.username = localStorage.getItem('username');
        this.selectedFile = null;
        this.projectType = 'binary';
        this.ws = null;
        this.boards = [];

        this.init();
    }

    init() {
        this.setupEventListeners();

        // Check if user has valid token stored
        if (this.token) {
            this.validateToken();
        } else {
            this.showLogin();
        }
    }

    async validateToken() {
        try {
            const response = await this.api('/api/auth/me');
            if (response.username) {
                this.username = response.username;
                this.showApp();
            } else {
                this.logout();
            }
        } catch (error) {
            this.logout();
        }
    }

    setupEventListeners() {
        // Login form
        document.getElementById('login-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.login();
        });

        // Logout button
        document.getElementById('logout-btn').addEventListener('click', () => this.logout());

        // Tab navigation
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchTab(btn.dataset.tab));
        });

        // Project type selector
        document.querySelectorAll('.project-type-btn').forEach(btn => {
            btn.addEventListener('click', () => this.setProjectType(btn.dataset.type));
        });

        // File upload
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('file-input');

        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('drag-over');
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            if (e.dataTransfer.files.length) {
                this.handleFile(e.dataTransfer.files[0]);
            }
        });
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) {
                this.handleFile(e.target.files[0]);
            }
        });

        // Clear file button
        document.getElementById('clear-file-btn').addEventListener('click', () => this.clearFile());

        // Flash button
        document.getElementById('flash-btn').addEventListener('click', () => this.flashFirmware());

        // Clear consoles
        document.getElementById('clear-console-btn').addEventListener('click', () => this.clearConsole());
        document.getElementById('clear-boards-console-btn').addEventListener('click', () => this.clearBoardsConsole());

        // Board management
        document.getElementById('scan-boards-btn').addEventListener('click', () => this.scanBoards());
        document.getElementById('discover-boards-btn').addEventListener('click', () => this.discoverBoards());
        document.getElementById('add-board-btn').addEventListener('click', () => this.showAddBoardModal());
        document.getElementById('close-add-board-modal').addEventListener('click', () => this.hideAddBoardModal());
        document.getElementById('cancel-add-board').addEventListener('click', () => this.hideAddBoardModal());

        // Add board forms
        document.getElementById('add-board-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.addBoard('add-board-form');
        });
        document.getElementById('modal-add-board-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.addBoard('modal-add-board-form');
            this.hideAddBoardModal();
        });

        // Refresh builds
        document.getElementById('refresh-builds-btn').addEventListener('click', () => this.loadBuilds());

        // Target board change
        document.getElementById('target-board').addEventListener('change', () => this.updateFlashButton());
    }

    async api(endpoint, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        const response = await fetch(endpoint, {
            ...options,
            headers,
        });

        if (response.status === 401) {
            this.logout();
            throw new Error('Unauthorized');
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'API error');
        }

        return data;
    }

    async login() {
        const username = document.getElementById('login-username').value;
        const password = document.getElementById('login-password').value;
        const errorEl = document.getElementById('login-error');

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            const data = await response.json();

            if (response.ok) {
                this.token = data.access_token;
                this.username = data.username;
                localStorage.setItem('token', this.token);
                localStorage.setItem('username', this.username);
                errorEl.classList.add('hidden');
                this.showApp();
            } else {
                errorEl.textContent = data.detail || 'Login failed';
                errorEl.classList.remove('hidden');
            }
        } catch (error) {
            errorEl.textContent = 'Connection error';
            errorEl.classList.remove('hidden');
        }
    }

    logout() {
        this.token = null;
        this.username = null;
        localStorage.removeItem('token');
        localStorage.removeItem('username');
        this.showLogin();
    }

    showLogin() {
        document.getElementById('login-modal').classList.remove('hidden');
        document.getElementById('app').classList.add('hidden');
    }

    showApp() {
        document.getElementById('login-modal').classList.add('hidden');
        document.getElementById('app').classList.remove('hidden');
        document.getElementById('current-user').textContent = this.username;

        this.loadBoards();
        this.connectWebSocket();
    }

    switchTab(tabName) {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('hidden', content.id !== `tab-${tabName}`);
        });

        if (tabName === 'boards') {
            this.loadBoards();
        } else if (tabName === 'builds') {
            this.loadBuilds();
        }
    }

    setProjectType(type) {
        this.projectType = type;
        document.querySelectorAll('.project-type-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.type === type);
        });

        const fileInput = document.getElementById('file-input');
        const fileHint = document.getElementById('file-hint');

        switch (type) {
            case 'binary':
                fileInput.accept = '.bin';
                fileHint.textContent = '.bin firmware file';
                break;
            case 'esphome':
                fileInput.accept = '.yaml,.yml';
                fileHint.textContent = '.yaml ESPHome configuration';
                break;
            case 'arduino':
                fileInput.accept = '.ino';
                fileHint.textContent = '.ino Arduino sketch';
                break;
            case 'platformio':
                fileInput.accept = '.zip';
                fileHint.textContent = '.zip PlatformIO project';
                break;
        }

        this.clearFile();
    }

    handleFile(file) {
        this.selectedFile = file;
        document.getElementById('selected-file').classList.remove('hidden');
        document.getElementById('selected-file-name').textContent = file.name;
        this.updateFlashButton();
    }

    clearFile() {
        this.selectedFile = null;
        document.getElementById('file-input').value = '';
        document.getElementById('selected-file').classList.add('hidden');
        this.updateFlashButton();
    }

    updateFlashButton() {
        const btn = document.getElementById('flash-btn');
        const targetBoard = document.getElementById('target-board').value;
        btn.disabled = !this.selectedFile || !targetBoard;
    }

    async loadBoards() {
        try {
            const data = await this.api('/api/boards');
            this.boards = data.boards;
            this.renderBoards();
            this.updateBoardSelector();
        } catch (error) {
            this.showToast('Failed to load boards', 'error');
        }
    }

    renderBoards() {
        const grid = document.getElementById('boards-grid');

        if (!this.boards.length) {
            grid.innerHTML = `
                <div class="col-span-full text-center py-8 text-gray-500">
                    No boards registered. Add a board to get started.
                </div>
            `;
            return;
        }

        grid.innerHTML = this.boards.map(board => `
            <div class="board-card bg-gray-800 rounded-xl p-4 border border-gray-700">
                <div class="flex items-center justify-between mb-3">
                    <h3 class="font-semibold truncate">${board.name}</h3>
                    <div class="status-indicator ${board.online ? 'online' : 'offline'}"></div>
                </div>
                <div class="text-sm text-gray-400 space-y-1">
                    <p>ID: ${String(board.id).padStart(2, '0')} &middot; ${board.type.toUpperCase()}</p>
                    ${board.hostname ? `<p class="text-gray-500 truncate" title="${board.hostname}">${board.hostname}</p>` : ''}
                    <div class="flex flex-wrap gap-1 mt-1">
                        <span class="port-badge web">WEB :${board.webserver_port}</span>
                        <span class="port-badge ota">OTA :${board.ota_port}</span>
                        <span class="port-badge api">API :${board.api_port}</span>
                    </div>
                </div>
                <div class="flex space-x-2 mt-4">
                    <button onclick="app.pingBoard('${board.name}')"
                            class="flex-1 py-1 text-sm bg-gray-700 hover:bg-gray-600 rounded transition-colors">
                        Ping
                    </button>
                    <button onclick="app.deleteBoard('${board.name}')"
                            class="px-3 py-1 text-sm bg-red-900 hover:bg-red-800 rounded transition-colors">
                        Delete
                    </button>
                </div>
            </div>
        `).join('');
    }

    updateBoardSelector() {
        const select = document.getElementById('target-board');
        select.innerHTML = '<option value="">Select a board...</option>' +
            this.boards.map(board => {
                const idStr = String(board.id).padStart(2, '0');
                const typeStr = board.type.toUpperCase();
                const statusStr = board.online ? 'Online' : 'Offline';
                const hostnameStr = board.hostname ? ` - ${board.hostname}` : '';
                const label = `${board.name} [ID:${idStr}] ${typeStr}${hostnameStr} (${statusStr})`;
                return `<option value="${board.name}">${label}</option>`;
            }).join('');
    }

    async scanBoards() {
        this.logBoardsConsole('Scanning boards...', 'info');
        try {
            const data = await this.api('/api/boards/scan');
            this.boards = data.boards.map(b => ({
                ...b,
                webserver_port: b.ports.webserver,
                ota_port: b.ports.ota,
                api_port: b.ports.api,
                hostname: b.hostname || '',
            }));
            this.renderBoards();
            this.updateBoardSelector();

            // Log per-board detail
            for (const b of data.boards) {
                const ota = b.ota_online ? 'OK' : 'FAIL';
                const web = b.web_online ? 'OK' : 'FAIL';
                const api = b.api_info?.api_available ? 'OK' : 'FAIL';
                const level = b.online ? 'success' : 'warning';
                this.logBoardsConsole(
                    `  ${b.name} [ID:${String(b.id).padStart(2,'0')}] OTA:${ota} WEB:${web} API:${api} (${b.hostname || b.host})`,
                    level
                );
            }

            const online = this.boards.filter(b => b.online).length;
            this.logBoardsConsole(`Scan complete: ${online}/${this.boards.length} boards online`, online > 0 ? 'success' : 'warning');
        } catch (error) {
            this.logBoardsConsole('Scan failed: ' + error.message, 'error');
        }
    }

    async discoverBoards() {
        this.logBoardsConsole('Discovering boards on network...', 'info');
        try {
            const data = await this.api('/api/boards/discover?auto_register=true');
            this.logBoardsConsole(
                `Discovery complete: ${data.total_found} found, ${data.new_boards} new`,
                'success'
            );
            if (data.auto_registered.length > 0) {
                this.logBoardsConsole(
                    `Auto-registered: ${data.auto_registered.join(', ')}`,
                    'success'
                );
            }
            await this.loadBoards();
        } catch (error) {
            this.logBoardsConsole('Discovery failed: ' + error.message, 'error');
        }
    }

    async pingBoard(boardName) {
        this.logBoardsConsole(`Pinging ${boardName}...`, 'info');
        try {
            const data = await this.api(`/api/boards/${boardName}/ping`, { method: 'POST' });
            const ota = data.ota_online ? 'OK' : 'FAIL';
            const web = data.web_online ? 'OK' : 'FAIL';
            const api = data.api_available ? 'OK' : 'FAIL';
            this.logBoardsConsole(
                `${boardName}: ${data.online ? 'Online' : 'Offline'} - OTA:${ota} WEB:${web} API:${api} (${data.hostname || data.host}:${data.port})`,
                data.online ? 'success' : 'warning'
            );
            await this.loadBoards();
        } catch (error) {
            this.logBoardsConsole(`Ping failed: ${error.message}`, 'error');
        }
    }

    async deleteBoard(boardName) {
        if (!confirm(`Delete board "${boardName}"?`)) return;

        try {
            await this.api(`/api/boards/${boardName}`, { method: 'DELETE' });
            this.showToast(`Board "${boardName}" deleted`, 'success');
            await this.loadBoards();
        } catch (error) {
            this.showToast('Failed to delete board', 'error');
        }
    }

    showAddBoardModal() {
        document.getElementById('add-board-modal').classList.remove('hidden');
    }

    hideAddBoardModal() {
        document.getElementById('add-board-modal').classList.add('hidden');
        document.getElementById('modal-add-board-form').reset();
    }

    async addBoard(formId) {
        const prefix = formId.includes('modal') ? 'modal-' : '';
        const name = document.getElementById(`${prefix}board-name`).value;
        const id = parseInt(document.getElementById(`${prefix}board-id`).value);
        const type = document.getElementById(`${prefix}board-type`).value;
        const host = document.getElementById(`${prefix}board-host`).value || null;
        const hostname = document.getElementById(`${prefix}board-hostname`).value || null;
        const api_key = document.getElementById(`${prefix}board-api-key`).value || null;

        try {
            await this.api('/api/boards', {
                method: 'POST',
                body: JSON.stringify({ name, id, type, host, hostname, api_key }),
            });
            this.showToast(`Board "${name}" added`, 'success');
            this.logBoardsConsole(`Board "${name}" added (ID: ${id}, Type: ${type})`, 'success');
            document.getElementById(formId).reset();
            await this.loadBoards();
        } catch (error) {
            this.showToast(error.message, 'error');
            this.logBoardsConsole(`Failed to add board: ${error.message}`, 'error');
        }
    }

    async flashFirmware() {
        const targetBoard = document.getElementById('target-board').value;

        if (!this.selectedFile || !targetBoard) {
            this.showToast('Select a file and target board', 'error');
            return;
        }

        this.logConsole(`Starting flash to ${targetBoard}...`, 'info');
        this.showProgress(true);
        this.updateProgress(0, 'Preparing...');

        const formData = new FormData();
        formData.append('file', this.selectedFile);
        formData.append('board_name', targetBoard);

        try {
            let endpoint = '/api/flash/upload';

            // If not a binary, need to build first
            if (this.projectType !== 'binary') {
                this.logConsole('Building firmware...', 'info');

                const buildFormData = new FormData();

                switch (this.projectType) {
                    case 'esphome':
                        buildFormData.append('yaml_file', this.selectedFile);
                        buildFormData.append('board_type', 'esp32');
                        endpoint = '/api/build/esphome';
                        break;
                    case 'arduino':
                        buildFormData.append('sketch_file', this.selectedFile);
                        buildFormData.append('board_type', 'esp32:esp32:esp32');
                        endpoint = '/api/build/arduino';
                        break;
                    case 'platformio':
                        buildFormData.append('project_zip', this.selectedFile);
                        endpoint = '/api/build/platformio';
                        break;
                }

                const buildResponse = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${this.token}` },
                    body: buildFormData,
                });

                const buildData = await buildResponse.json();

                if (!buildResponse.ok) {
                    throw new Error(buildData.detail || 'Build failed');
                }

                this.logConsole(`Build started: ${buildData.build_id}`, 'info');

                // Poll for build completion
                const firmware = await this.waitForBuild(buildData.build_id);

                if (!firmware) {
                    throw new Error('Build failed');
                }

                // Flash the built firmware
                this.logConsole('Flashing firmware...', 'info');
                const flashResponse = await fetch('/api/flash/from-build', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.token}`,
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        board_name: targetBoard,
                        build_id: buildData.build_id,
                    }),
                });

                const flashData = await flashResponse.json();

                if (!flashResponse.ok) {
                    throw new Error(flashData.detail || 'Flash failed');
                }

                await this.waitForFlash(flashData.flash_id);
            } else {
                // Direct binary upload
                const response = await fetch('/api/flash/upload', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${this.token}` },
                    body: formData,
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || 'Upload failed');
                }

                await this.waitForFlash(data.flash_id);
            }

        } catch (error) {
            this.logConsole(`Error: ${error.message}`, 'error');
            this.showProgress(false);
        }
    }

    async waitForBuild(buildId) {
        const maxAttempts = 120; // 2 minutes
        let attempt = 0;

        while (attempt < maxAttempts) {
            try {
                const status = await this.api(`/api/build/status/${buildId}`);

                this.updateProgress(
                    status.status === 'building' ? 30 : 50,
                    `Building: ${status.status}`
                );

                if (status.status === 'success') {
                    this.logConsole('Build successful!', 'success');
                    return status.firmware_path;
                } else if (status.status === 'failed') {
                    this.logConsole('Build failed: ' + (status.message || 'Unknown error'), 'error');
                    if (status.logs) {
                        this.logConsole(status.logs, 'error');
                    }
                    return null;
                }

                await new Promise(resolve => setTimeout(resolve, 1000));
                attempt++;
            } catch (error) {
                this.logConsole('Error checking build status', 'error');
                return null;
            }
        }

        this.logConsole('Build timed out', 'error');
        return null;
    }

    async waitForFlash(flashId) {
        const maxAttempts = 120;
        let attempt = 0;

        while (attempt < maxAttempts) {
            try {
                const status = await this.api(`/api/flash/status/${flashId}`);

                this.updateProgress(
                    50 + (status.progress / 2),
                    status.message || `Flashing: ${status.status}`
                );

                if (status.status === 'success') {
                    this.logConsole('Flash successful! Board is rebooting...', 'success');
                    this.updateProgress(100, 'Complete!');
                    setTimeout(() => this.showProgress(false), 2000);
                    return true;
                } else if (status.status === 'failed') {
                    this.logConsole('Flash failed: ' + (status.message || 'Unknown error'), 'error');
                    this.showProgress(false);
                    return false;
                }

                await new Promise(resolve => setTimeout(resolve, 500));
                attempt++;
            } catch (error) {
                this.logConsole('Error checking flash status', 'error');
                this.showProgress(false);
                return false;
            }
        }

        this.logConsole('Flash timed out', 'error');
        this.showProgress(false);
        return false;
    }

    async loadBuilds() {
        try {
            const data = await this.api('/api/build/list');
            this.renderBuilds(data.builds);
        } catch (error) {
            this.showToast('Failed to load builds', 'error');
        }
    }

    renderBuilds(builds) {
        const list = document.getElementById('builds-list');

        if (!builds.length) {
            list.innerHTML = `
                <div class="text-center py-8 text-gray-500">
                    No builds yet. Upload a project to start building.
                </div>
            `;
            return;
        }

        list.innerHTML = builds.map(build => `
            <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
                <div class="flex items-center justify-between">
                    <div>
                        <span class="font-mono text-sm">${build.build_id}</span>
                        <span class="badge badge-${build.status} ml-2">${build.status}</span>
                    </div>
                    ${build.status === 'success' ? `
                        <button onclick="app.flashBuild('${build.build_id}')"
                                class="px-3 py-1 text-sm bg-cactus-600 hover:bg-cactus-700 rounded transition-colors">
                            Flash
                        </button>
                    ` : ''}
                </div>
                ${build.message ? `<p class="text-sm text-gray-400 mt-2">${build.message}</p>` : ''}
            </div>
        `).join('');
    }

    async flashBuild(buildId) {
        const targetBoard = prompt('Enter target board name:');
        if (!targetBoard) return;

        this.logConsole(`Flashing build ${buildId} to ${targetBoard}...`, 'info');
        this.showProgress(true);

        try {
            const response = await fetch('/api/flash/from-build', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    board_name: targetBoard,
                    build_id: buildId,
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Flash failed');
            }

            await this.waitForFlash(data.flash_id);
        } catch (error) {
            this.logConsole(`Error: ${error.message}`, 'error');
            this.showProgress(false);
        }
    }

    connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWSMessage(data);
            } catch (e) {
                console.error('WebSocket message error:', e);
            }
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected, reconnecting...');
            setTimeout(() => this.connectWebSocket(), 3000);
        };
    }

    handleWSMessage(data) {
        switch (data.type) {
            case 'log':
                this.logConsole(data.data.message, data.data.level || 'info');
                break;
            case 'progress':
                this.updateProgress(data.data.percent, data.data.message);
                break;
            case 'status':
                if (data.data.board) {
                    this.loadBoards();
                }
                break;
        }
    }

    showProgress(show) {
        document.getElementById('progress-container').classList.toggle('hidden', !show);
    }

    updateProgress(percent, message) {
        document.getElementById('progress-bar').style.width = `${percent}%`;
        document.getElementById('progress-percent').textContent = `${Math.round(percent)}%`;
        document.getElementById('progress-status').textContent = message;
    }

    logConsole(message, level = 'info') {
        const console = document.getElementById('console-output');
        const time = new Date().toLocaleTimeString();
        const line = document.createElement('p');
        line.className = `log-${level}`;
        line.textContent = `[${time}] ${message}`;
        console.appendChild(line);
        console.scrollTop = console.scrollHeight;
    }

    clearConsole() {
        document.getElementById('console-output').innerHTML =
            '<p class="text-gray-500">Console cleared.</p>';
    }

    logBoardsConsole(message, level = 'info') {
        const consoleEl = document.getElementById('boards-console-output');
        const time = new Date().toLocaleTimeString();
        const line = document.createElement('p');
        line.className = `log-${level}`;
        line.textContent = `[${time}] ${message}`;
        consoleEl.appendChild(line);
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    clearBoardsConsole() {
        document.getElementById('boards-console-output').innerHTML =
            '<p class="text-gray-500">Console cleared.</p>';
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
}

// Initialize app
const app = new CactusFlasher();
