// Cactus Flasher - Frontend Application

class CactusFlasher {
    constructor() {
        this.token = localStorage.getItem('token');
        this.username = localStorage.getItem('username');
        this.selectedFiles = [];
        this.projectType = 'binary';
        this.ws = null;
        this.boards = [];
        this.liveLogSource = null;
        this.liveLogBoardName = null;
        this.liveLogFilter = 'all';
        this.liveLogCount = 0;
        this.maximizedPanel = null; // null, 'ops-log', 'live-logs'

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
                this.handleFiles(e.dataTransfer.files);
            }
        });
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) {
                this.handleFiles(e.target.files);
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

        // Edit board modal
        document.getElementById('close-edit-board-modal').addEventListener('click', () => this.hideEditBoardModal());
        document.getElementById('cancel-edit-board').addEventListener('click', () => this.hideEditBoardModal());
        document.getElementById('edit-board-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveEditBoard();
        });

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

        // User management forms
        document.getElementById('register-user-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.registerUser();
        });
        document.getElementById('change-password-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.changePassword();
        });

        // Password strength indicators
        document.getElementById('reg-password').addEventListener('input', (e) => {
            this.showPasswordStrength(e.target.value, 'reg-password-strength');
        });
        document.getElementById('cp-new-password').addEventListener('input', (e) => {
            this.showPasswordStrength(e.target.value, 'cp-password-strength');
        });

        // Connection History collapsible
        document.getElementById('toggle-status-log').addEventListener('click', () => {
            this.toggleSection('status-log-body', 'status-log-chevron');
        });

        // Status log refresh + clear
        const refreshLogBtn = document.getElementById('refresh-status-log-btn');
        if (refreshLogBtn) {
            refreshLogBtn.addEventListener('click', () => this.loadStatusLog());
        }
        const clearAllLogBtn = document.getElementById('clear-all-status-log-btn');
        if (clearAllLogBtn) {
            clearAllLogBtn.addEventListener('click', () => this.clearAllStatusLogs());
        }

        // Live logs controls
        const stopLogsBtn = document.getElementById('stop-live-logs-btn');
        if (stopLogsBtn) {
            stopLogsBtn.addEventListener('click', () => this.stopBoardLogs());
        }
        const downloadLogsBtn = document.getElementById('download-live-logs-btn');
        if (downloadLogsBtn) {
            downloadLogsBtn.addEventListener('click', () => this.downloadLogs('live-logs-output', `live-logs-${this.liveLogBoardName || 'board'}`));
        }
        const liveLogsFilter = document.getElementById('live-logs-filter');
        if (liveLogsFilter) {
            liveLogsFilter.addEventListener('change', (e) => {
                this.liveLogFilter = e.target.value;
                this.applyLiveLogFilter();
            });
        }

        // Console save buttons
        const saveBoardsBtn = document.getElementById('save-boards-console-btn');
        if (saveBoardsBtn) {
            saveBoardsBtn.addEventListener('click', () => this.downloadLogs('boards-console-output', 'boards-log'));
        }
        const saveConsoleBtn = document.getElementById('save-console-btn');
        if (saveConsoleBtn) {
            saveConsoleBtn.addEventListener('click', () => this.downloadLogs('console-output', 'flash-log'));
        }

        // Panel maximize buttons
        const maxOpsBtn = document.getElementById('maximize-ops-log-btn');
        if (maxOpsBtn) {
            maxOpsBtn.addEventListener('click', () => this.togglePanelMaximize('ops-log'));
        }
        const maxLiveBtn = document.getElementById('maximize-live-logs-btn');
        if (maxLiveBtn) {
            maxLiveBtn.addEventListener('click', () => this.togglePanelMaximize('live-logs'));
        }
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
        this.loadStatusLog();
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
            this.loadStatusLog();
        } else if (tabName === 'builds') {
            this.loadBuilds();
        } else if (tabName === 'settings') {
            this.loadUsers();
        }
    }

    // ==================== File Handling ====================

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
                fileInput.removeAttribute('multiple');
                fileHint.textContent = '.bin firmware file';
                break;
            case 'esphome':
                fileInput.accept = '.yaml,.yml,.zip,.html,.css,.js';
                fileInput.setAttribute('multiple', '');
                fileHint.textContent = '.yaml + companion files (HTML/CSS/JS) or .zip archive';
                break;
            case 'arduino':
                fileInput.accept = '.ino,.h,.cpp,.c';
                fileInput.setAttribute('multiple', '');
                fileHint.textContent = '.ino sketch + optional .h/.cpp library files';
                break;
            case 'platformio':
                fileInput.accept = '.zip';
                fileInput.removeAttribute('multiple');
                fileHint.textContent = '.zip PlatformIO project';
                break;
        }

        this.clearFile();
    }

    handleFiles(fileList) {
        const files = Array.from(fileList);

        if (this.projectType === 'binary' || this.projectType === 'platformio') {
            // Single file mode
            this.selectedFiles = [files[0]];
        } else if (this.projectType === 'esphome') {
            // ESPHome: .yaml as main + optional companion files, or single .zip
            if (files.length === 1 && files[0].name.endsWith('.zip')) {
                this.selectedFiles = [files[0]];
            } else {
                // Merge with existing if adding more files
                const newFiles = files.filter(f => !this.selectedFiles.some(e => e.name === f.name));
                this.selectedFiles = [...this.selectedFiles, ...newFiles];
            }
        } else if (this.projectType === 'arduino') {
            // Arduino: .ino as main + optional library files
            const newFiles = files.filter(f => !this.selectedFiles.some(e => e.name === f.name));
            this.selectedFiles = [...this.selectedFiles, ...newFiles];
        }

        this.renderSelectedFiles();
        this.updateFlashButton();
    }

    renderSelectedFiles() {
        const container = document.getElementById('selected-files');
        const countEl = document.getElementById('selected-files-count');
        const listEl = document.getElementById('selected-files-list');

        if (!this.selectedFiles.length) {
            container.classList.add('hidden');
            return;
        }

        container.classList.remove('hidden');
        countEl.textContent = `${this.selectedFiles.length} file${this.selectedFiles.length > 1 ? 's' : ''} selected`;

        listEl.innerHTML = this.selectedFiles.map((f, i) => {
            const sizeKB = (f.size / 1024).toFixed(1);
            const isMain = i === 0;
            const badge = isMain ? '<span class="text-cactus-400 text-xs ml-1">(main)</span>' : '';
            return `<div class="flex items-center justify-between py-0.5">
                <span class="truncate">${f.name}${badge}</span>
                <span class="text-gray-500 ml-2 flex-shrink-0">${sizeKB} KB</span>
            </div>`;
        }).join('');
    }

    clearFile() {
        this.selectedFiles = [];
        document.getElementById('file-input').value = '';
        document.getElementById('selected-files').classList.add('hidden');
        this.updateFlashButton();
    }

    updateFlashButton() {
        const btn = document.getElementById('flash-btn');
        const targetBoard = document.getElementById('target-board').value;
        btn.disabled = !this.selectedFiles.length || !targetBoard;
    }

    // ==================== Board Management ====================

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

        grid.innerHTML = this.boards.map(board => {
            const idStr = String(board.id).padStart(2, '0');
            const typeStr = board.type.toUpperCase();

            // Build sensor display
            let sensorsHtml = '';
            if (board.sensors && board.sensors.length > 0) {
                const displayed = board.sensors.slice(0, 4);
                const remaining = board.sensors.length - displayed.length;
                sensorsHtml = `
                    <div class="mt-2 pt-2 border-t border-gray-700/50">
                        <p class="text-xs text-gray-500 mb-1">Sensors (${board.sensors.length})</p>
                        <div class="flex flex-wrap gap-1">
                            ${displayed.map(s =>
                                `<span class="sensor-badge">${s.name}: ${s.state || '?'}${s.unit ? ' ' + s.unit : ''}</span>`
                            ).join('')}
                            ${remaining > 0 ? `<span class="text-gray-600 text-xs">+${remaining} more</span>` : ''}
                        </div>
                    </div>`;
            }

            // Device info display (persisted from last scan, shown even when offline)
            const di = board.device_info || {};
            let deviceInfoHtml = '';
            const diParts = [];
            if (di.esphome_version) diParts.push(`v${di.esphome_version}`);
            if (di.platform) diParts.push(di.platform);
            if (di.ip_address) diParts.push(di.ip_address);
            if (diParts.length > 0) {
                deviceInfoHtml = `<p class="text-gray-600 text-xs">${diParts.join(' &middot; ')}</p>`;
            }

            // Last seen display (only for offline boards)
            let lastSeenHtml = '';
            if (!board.online && board.last_seen) {
                const lastDate = new Date(board.last_seen);
                lastSeenHtml = `<p class="text-gray-600 text-xs mt-1">Last seen: ${lastDate.toLocaleString()}</p>`;
            }

            // Tooltip content for board name hover
            const tooltipLines = [
                `<strong>${board.name}</strong>`,
                `ID: ${idStr} | Type: ${typeStr}`,
                `Host: ${board.hostname || board.host}`,
                `WEB: :${board.webserver_port} | OTA: :${board.ota_port} | API: :${board.api_port}`,
            ];
            if (board.mac_address) tooltipLines.push(`MAC: ${board.mac_address}`);
            if (di.esphome_version) tooltipLines.push(`ESPHome: ${di.esphome_version}`);
            if (di.platform) tooltipLines.push(`Platform: ${di.platform}`);
            if (di.board_model) tooltipLines.push(`Board: ${di.board_model}`);
            if (di.wifi_ssid) tooltipLines.push(`WiFi: ${di.wifi_ssid}`);
            if (di.ip_address) tooltipLines.push(`IP: ${di.ip_address}`);
            if (di.compiled) tooltipLines.push(`Compiled: ${di.compiled}`);
            if (board.last_seen) tooltipLines.push(`Last seen: ${new Date(board.last_seen).toLocaleString()}`);
            if (board.sensors && board.sensors.length) tooltipLines.push(`Sensors: ${board.sensors.length}`);
            const tooltipContent = tooltipLines.join('<br>');

            return `
            <div class="board-card bg-gray-800 rounded-xl p-4 border border-gray-700">
                <div class="flex items-center justify-between mb-3">
                    <div class="tooltip-wrapper flex-1 min-w-0">
                        <h3 class="font-semibold truncate">${board.name}</h3>
                        <div class="tooltip-text tooltip-wide tooltip-bottom">${tooltipContent}</div>
                    </div>
                    <div class="tooltip-wrapper ml-2">
                        <div class="status-indicator ${board.online ? 'online' : 'offline'}"></div>
                        <span class="tooltip-text">${board.online ? 'Board is online and reachable' : 'Board is offline or unreachable'}</span>
                    </div>
                </div>
                <div class="text-sm text-gray-400 space-y-1">
                    <p>ID: ${idStr} &middot; ${typeStr}</p>
                    ${board.hostname ? `<p class="text-gray-500 truncate" title="${board.hostname}">${board.hostname}</p>` : ''}
                    ${board.mac_address ? `<p class="text-gray-500 font-mono text-xs cursor-pointer" title="Click to copy MAC address" onclick="navigator.clipboard.writeText('${board.mac_address}').then(()=>app.showToast('MAC copied','success'))">${board.mac_address}</p>` : ''}
                    ${deviceInfoHtml}
                    ${lastSeenHtml}
                    <div class="flex flex-wrap gap-1 mt-1">
                        <div class="tooltip-wrapper">
                            <span class="port-badge web">WEB :${board.webserver_port}</span>
                            <span class="tooltip-text">Webserver port for browser access</span>
                        </div>
                        <div class="tooltip-wrapper">
                            <span class="port-badge ota">OTA :${board.ota_port}</span>
                            <span class="tooltip-text">OTA port for firmware updates</span>
                        </div>
                        <div class="tooltip-wrapper">
                            <span class="port-badge api">API :${board.api_port}</span>
                            <span class="tooltip-text">ESPHome Native API port</span>
                        </div>
                    </div>
                    ${sensorsHtml}
                </div>
                <div class="flex space-x-2 mt-4">
                    <button onclick="app.flashBoard('${board.name}')"
                            class="flex-1 py-1 text-sm bg-cactus-600 hover:bg-cactus-700 rounded transition-colors ${!board.online ? 'opacity-50 cursor-not-allowed' : ''}"
                            ${!board.online ? 'disabled' : ''}>
                        Flash
                    </button>
                    <button onclick="app.streamBoardLogs('${board.name}')"
                            class="px-3 py-1 text-sm bg-blue-700 hover:bg-blue-600 rounded transition-colors ${!board.online ? 'opacity-50 cursor-not-allowed' : ''}"
                            ${!board.online ? 'disabled' : ''}
                            title="Stream live logs from board">
                        Logs
                    </button>
                    <button onclick="app.pingBoard('${board.name}')"
                            class="flex-1 py-1 text-sm bg-gray-700 hover:bg-gray-600 rounded transition-colors">
                        Ping
                    </button>
                    <button onclick="app.showEditBoardModal('${board.name}')"
                            class="px-3 py-1 text-sm bg-gray-700 hover:bg-gray-600 rounded transition-colors"
                            title="Edit board settings">
                        &#9998;
                    </button>
                    <button onclick="app.deleteBoard('${board.name}')"
                            class="px-3 py-1 text-sm bg-red-900 hover:bg-red-800 rounded transition-colors">
                        Delete
                    </button>
                </div>
            </div>
        `}).join('');
    }

    updateBoardSelector() {
        const select = document.getElementById('target-board');
        select.innerHTML = '<option value="">Select a board...</option>' +
            this.boards.map(board => {
                const idStr = String(board.id).padStart(2, '0');
                const typeStr = board.type.toUpperCase();
                const statusStr = board.online ? 'Online' : 'Offline';
                const hostnameStr = board.hostname ? ` - ${board.hostname}` : '';
                const macStr = board.mac_address ? ` | ${board.mac_address}` : '';
                const label = `${board.name} [ID:${idStr}] ${typeStr}${hostnameStr}${macStr} (${statusStr})`;
                return `<option value="${board.name}">${label}</option>`;
            }).join('');
    }

    // Flash board from dashboard - switches to Upload tab with board pre-selected
    flashBoard(boardName) {
        this.switchTab('upload');

        // Pre-select the target board
        const select = document.getElementById('target-board');
        select.value = boardName;
        this.updateFlashButton();

        this.showToast(`Target: ${boardName} - select firmware to flash`, 'info');
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
                mac_address: b.mac_address || null,
                sensors: b.sensors || [],
            }));
            this.renderBoards();
            this.updateBoardSelector();

            // Log per-board detail
            for (const b of data.boards) {
                const ota = b.ota_online ? 'OK' : 'FAIL';
                const web = b.web_online ? 'OK' : 'FAIL';
                const api = b.api_info?.api_available ? 'OK' : 'FAIL';
                const level = b.online ? 'success' : 'warning';
                const mac = b.mac_address ? ` MAC:${b.mac_address}` : '';
                const sensorCount = b.sensors && b.sensors.length ? ` Sensors:${b.sensors.length}` : '';
                this.logBoardsConsole(
                    `  ${b.name} [ID:${String(b.id).padStart(2,'0')}] OTA:${ota} WEB:${web} API:${api}${mac}${sensorCount} (${b.hostname || b.host})`,
                    level
                );
            }

            const online = this.boards.filter(b => b.online).length;
            this.logBoardsConsole(`Scan complete: ${online}/${this.boards.length} boards online`, online > 0 ? 'success' : 'warning');

            // Refresh status log after scan
            this.loadStatusLog();
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
            const mac = data.mac_address ? ` MAC:${data.mac_address}` : '';
            this.logBoardsConsole(
                `${boardName}: ${data.online ? 'Online' : 'Offline'} - OTA:${ota} WEB:${web} API:${api}${mac} (${data.hostname || data.host}:${data.port})`,
                data.online ? 'success' : 'warning'
            );
            await this.loadBoards();
            this.loadStatusLog();
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

    // ==================== Live Board Logs ====================

    streamBoardLogs(boardName) {
        // Stop existing stream if any
        this.stopBoardLogs();

        const panel = document.getElementById('live-logs-panel');
        const output = document.getElementById('live-logs-output');
        const nameEl = document.getElementById('live-logs-board-name');
        const maxOpsBtn = document.getElementById('maximize-ops-log-btn');

        panel.classList.remove('hidden');
        nameEl.textContent = boardName;
        output.innerHTML = '<p class="text-gray-500">Connecting...</p>';

        // Show maximize button on ops log since we're now in split mode
        if (maxOpsBtn) maxOpsBtn.classList.remove('hidden');

        this.liveLogBoardName = boardName;
        this.liveLogCount = 0;
        this.liveLogFilter = 'all';
        this.maximizedPanel = null;
        const filterEl = document.getElementById('live-logs-filter');
        if (filterEl) filterEl.value = 'all';

        const url = `/api/boards/${encodeURIComponent(boardName)}/logs`;
        this.liveLogSource = new EventSource(url);

        this.liveLogSource.onopen = () => {
            output.innerHTML = '';
            this.logLivePanel('Connected, waiting for events...', 'info');
        };

        this.liveLogSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.error) {
                    this.logLivePanel(`Error: ${data.error}`, 'error');
                    return;
                }
                const id = data.id || '';
                const state = data.state !== undefined ? data.state : (data.value || '');
                // Color code by entity type
                let level = 'sensor';
                if (id.startsWith('switch-') || id.startsWith('light-') || id.startsWith('fan-')) {
                    level = 'switch';
                } else if (id.startsWith('binary_sensor-')) {
                    level = 'binary';
                } else if (id.startsWith('text_sensor-')) {
                    level = 'text';
                }
                this.logLivePanel(`${id}: ${state}`, level);
            } catch (e) {
                // Raw text event
                if (event.data.trim()) {
                    this.logLivePanel(event.data, 'log');
                }
            }
        };

        this.liveLogSource.addEventListener('state', (event) => {
            try {
                const data = JSON.parse(event.data);
                const id = data.id || '?';
                const state = data.state !== undefined ? data.state : (data.value || '');
                let level = 'sensor';
                if (id.startsWith('switch-') || id.startsWith('light-') || id.startsWith('fan-')) {
                    level = 'switch';
                } else if (id.startsWith('binary_sensor-')) {
                    level = 'binary';
                } else if (id.startsWith('text_sensor-')) {
                    level = 'text';
                }
                this.logLivePanel(`${id}: ${state}`, level);
            } catch (e) {
                this.logLivePanel(event.data, 'log');
            }
        });

        this.liveLogSource.addEventListener('log', (event) => {
            try {
                const data = JSON.parse(event.data);
                const msg = data.message || event.data;
                const lvl = data.level || 'info';
                this.logLivePanel(msg, lvl === 'ERROR' ? 'error' : lvl === 'WARNING' ? 'warning' : 'log');
            } catch (e) {
                this.logLivePanel(event.data, 'log');
            }
        });

        this.liveLogSource.addEventListener('ping', (event) => {
            // ESPHome sends periodic ping events - show as debug
            this.logLivePanel('ping', 'log');
        });

        this.liveLogSource.onerror = () => {
            this.logLivePanel('Connection lost. Retrying...', 'error');
        };

        this.logBoardsConsole(`Streaming logs from ${boardName}...`, 'info');
    }

    stopBoardLogs() {
        if (this.liveLogSource) {
            this.liveLogSource.close();
            this.liveLogSource = null;
        }
        if (this.liveLogBoardName) {
            this.logBoardsConsole(`Stopped log stream from ${this.liveLogBoardName}`, 'info');
            this.liveLogBoardName = null;
        }
        const panel = document.getElementById('live-logs-panel');
        if (panel) panel.classList.add('hidden');

        // Hide maximize button on ops log, reset to full width
        const maxOpsBtn = document.getElementById('maximize-ops-log-btn');
        if (maxOpsBtn) maxOpsBtn.classList.add('hidden');

        // Reset maximized state
        this.maximizedPanel = null;
        const opsPanel = document.getElementById('ops-log-panel');
        if (opsPanel) {
            opsPanel.classList.remove('hidden');
            opsPanel.style.flex = '';
        }
    }

    // ==================== Panel Maximize/Minimize ====================

    togglePanelMaximize(panelId) {
        const opsPanel = document.getElementById('ops-log-panel');
        const livePanel = document.getElementById('live-logs-panel');
        if (!opsPanel || !livePanel) return;

        if (this.maximizedPanel === panelId) {
            // Restore side-by-side
            this.maximizedPanel = null;
            opsPanel.classList.remove('hidden');
            livePanel.classList.remove('hidden');
            opsPanel.style.flex = '';
            livePanel.style.flex = '';
        } else {
            // Maximize the selected panel
            this.maximizedPanel = panelId;
            if (panelId === 'ops-log') {
                opsPanel.classList.remove('hidden');
                livePanel.classList.add('hidden');
            } else {
                livePanel.classList.remove('hidden');
                opsPanel.classList.add('hidden');
            }
        }
    }

    logLivePanel(message, level = 'info') {
        const output = document.getElementById('live-logs-output');
        if (!output) return;
        const time = new Date().toLocaleTimeString();
        const line = document.createElement('p');
        line.className = `log-live-${level}`;
        line.dataset.level = level;
        line.textContent = `[${time}] ${message}`;

        // Apply current filter
        if (this.liveLogFilter !== 'all' && level !== this.liveLogFilter) {
            line.style.display = 'none';
        }

        output.appendChild(line);
        this.liveLogCount++;

        // Update counter
        const countEl = document.getElementById('live-logs-count');
        if (countEl) countEl.textContent = `(${this.liveLogCount} events)`;

        // Keep max 1000 lines
        while (output.children.length > 1000) {
            output.removeChild(output.firstChild);
        }
        output.scrollTop = output.scrollHeight;
    }

    applyLiveLogFilter() {
        const output = document.getElementById('live-logs-output');
        if (!output) return;
        for (const line of output.children) {
            const level = line.dataset.level;
            if (this.liveLogFilter === 'all' || level === this.liveLogFilter) {
                line.style.display = '';
            } else {
                line.style.display = 'none';
            }
        }
        output.scrollTop = output.scrollHeight;
    }

    downloadLogs(containerId, filenamePrefix) {
        const container = document.getElementById(containerId);
        if (!container) return;
        const lines = [];
        for (const child of container.children) {
            if (child.style.display !== 'none') {
                lines.push(child.textContent);
            }
        }
        if (!lines.length) {
            this.showToast('No logs to save', 'error');
            return;
        }
        const text = lines.join('\n');
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const filename = `${filenamePrefix}-${timestamp}.txt`;
        const blob = new Blob([text], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        this.showToast(`Saved ${lines.length} lines to ${filename}`, 'success');
    }

    showAddBoardModal() {
        document.getElementById('add-board-modal').classList.remove('hidden');
    }

    hideAddBoardModal() {
        document.getElementById('add-board-modal').classList.add('hidden');
        document.getElementById('modal-add-board-form').reset();
    }

    async showEditBoardModal(boardName) {
        try {
            const board = await this.api(`/api/boards/${encodeURIComponent(boardName)}`);
            document.getElementById('edit-board-original-name').value = boardName;
            document.getElementById('edit-board-title').textContent = boardName;
            document.getElementById('edit-board-id').value = board.id || '';
            document.getElementById('edit-board-type').value = board.type || 'esp32';
            document.getElementById('edit-board-host').value = board.host || '';
            document.getElementById('edit-board-hostname').value = board.hostname || '';
            document.getElementById('edit-board-mac').value = board.mac_address || '';
            document.getElementById('edit-board-api-key').value = board.api_key || '';
            document.getElementById('edit-board-web-username').value = board.web_username || '';
            document.getElementById('edit-board-web-password').value = board.web_password || '';
            document.getElementById('edit-board-modal').classList.remove('hidden');
        } catch (error) {
            this.showToast('Failed to load board data: ' + error.message, 'error');
        }
    }

    hideEditBoardModal() {
        document.getElementById('edit-board-modal').classList.add('hidden');
        document.getElementById('edit-board-form').reset();
    }

    async saveEditBoard() {
        const originalName = document.getElementById('edit-board-original-name').value;
        const data = {
            type: document.getElementById('edit-board-type').value,
            host: document.getElementById('edit-board-host').value || null,
            hostname: document.getElementById('edit-board-hostname').value || null,
            mac_address: document.getElementById('edit-board-mac').value || null,
            api_key: document.getElementById('edit-board-api-key').value || null,
            web_username: document.getElementById('edit-board-web-username').value || null,
            web_password: document.getElementById('edit-board-web-password').value || null,
        };

        try {
            await this.api(`/api/boards/${encodeURIComponent(originalName)}`, {
                method: 'PUT',
                body: JSON.stringify(data),
            });
            this.showToast(`Board "${originalName}" updated`, 'success');
            this.logBoardsConsole(`Board "${originalName}" updated`, 'success');
            this.hideEditBoardModal();
            await this.loadBoards();
        } catch (error) {
            this.showToast('Failed to update board: ' + error.message, 'error');
        }
    }

    async addBoard(formId) {
        const prefix = formId.includes('modal') ? 'modal-' : '';
        const name = document.getElementById(`${prefix}board-name`).value;
        const id = parseInt(document.getElementById(`${prefix}board-id`).value);
        const type = document.getElementById(`${prefix}board-type`).value;
        const host = document.getElementById(`${prefix}board-host`).value || null;
        const hostname = document.getElementById(`${prefix}board-hostname`).value || null;
        const api_key = document.getElementById(`${prefix}board-api-key`).value || null;
        const mac_address = document.getElementById(`${prefix}board-mac`).value || null;
        const web_username = document.getElementById(`${prefix}board-web-username`).value || null;
        const web_password = document.getElementById(`${prefix}board-web-password`).value || null;

        try {
            await this.api('/api/boards', {
                method: 'POST',
                body: JSON.stringify({ name, id, type, host, hostname, api_key, mac_address, web_username, web_password }),
            });
            this.showToast(`Board "${name}" added`, 'success');
            this.logBoardsConsole(`Board "${name}" added (ID: ${id}, Type: ${type}${mac_address ? ', MAC: ' + mac_address : ''})`, 'success');
            document.getElementById(formId).reset();
            await this.loadBoards();
        } catch (error) {
            this.showToast(error.message, 'error');
            this.logBoardsConsole(`Failed to add board: ${error.message}`, 'error');
        }
    }

    // ==================== Status Log ====================

    async loadStatusLog() {
        try {
            const data = await this.api('/api/boards/status-log?limit=50');
            this.renderStatusLog(data.logs);
        } catch (error) {
            // Silently fail - status log is non-critical
        }
    }

    renderStatusLog(logs) {
        const container = document.getElementById('status-log-container');
        if (!container) return;

        if (!logs || !logs.length) {
            container.innerHTML = '<p class="text-gray-500 text-sm">No status changes recorded yet. Run a scan to start tracking.</p>';
            return;
        }

        container.innerHTML = `
            <table class="w-full text-sm">
                <thead>
                    <tr class="border-b border-gray-700">
                        <th class="text-left py-1.5 text-gray-400 font-medium">Time</th>
                        <th class="text-left py-1.5 text-gray-400 font-medium">Board</th>
                        <th class="text-left py-1.5 text-gray-400 font-medium">Status</th>
                        <th class="text-left py-1.5 text-gray-400 font-medium hidden sm:table-cell">Details</th>
                        <th class="w-8"></th>
                    </tr>
                </thead>
                <tbody>
                    ${logs.map(log => {
                        const time = new Date(log.timestamp).toLocaleString();
                        const isOnline = log.event === 'online';
                        return `
                            <tr class="border-b border-gray-700/30">
                                <td class="py-1.5 text-gray-500 text-xs">${time}</td>
                                <td class="py-1.5 font-medium">${log.board_name}</td>
                                <td class="py-1.5">
                                    <span class="badge badge-${isOnline ? 'online' : 'offline'}">${log.event}</span>
                                </td>
                                <td class="py-1.5 text-gray-500 text-xs font-mono hidden sm:table-cell">${log.details || ''}</td>
                                <td class="py-1.5 text-right">
                                    <button onclick="app.deleteStatusLogEntry('${log.timestamp}', '${log.board_name}')"
                                            class="status-log-delete-btn text-red-500 hover:text-red-300 text-lg leading-none"
                                            title="Delete entry">&times;</button>
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    }

    toggleSection(bodyId, chevronId) {
        const body = document.getElementById(bodyId);
        const chevron = document.getElementById(chevronId);
        if (!body || !chevron) return;
        const isHidden = body.classList.contains('hidden');
        body.classList.toggle('hidden', !isHidden);
        chevron.style.transform = isHidden ? '' : 'rotate(-90deg)';
    }

    async clearAllStatusLogs() {
        if (!confirm('Clear all connection history entries?')) return;
        try {
            await this.api('/api/boards/status-log', { method: 'DELETE' });
            this.showToast('Connection history cleared', 'success');
            this.loadStatusLog();
        } catch (error) {
            this.showToast('Failed to clear history: ' + error.message, 'error');
        }
    }

    async deleteStatusLogEntry(timestamp, boardName) {
        try {
            await this.api(`/api/boards/status-log/entry?timestamp=${encodeURIComponent(timestamp)}&board_name=${encodeURIComponent(boardName)}`, { method: 'DELETE' });
            this.loadStatusLog();
        } catch (error) {
            this.showToast('Failed to delete entry', 'error');
        }
    }

    // ==================== Flash / Build ====================

    async flashFirmware() {
        const targetBoard = document.getElementById('target-board').value;

        if (!this.selectedFiles.length || !targetBoard) {
            this.showToast('Select a file and target board', 'error');
            return;
        }

        const mainFile = this.selectedFiles[0];
        const companionFiles = this.selectedFiles.slice(1);

        this.logConsole(`Starting flash to ${targetBoard}...`, 'info');
        this.showProgress(true);
        this.updateProgress(0, 'Preparing...');

        try {
            let endpoint = '/api/flash/upload';

            // If not a binary, need to build first
            if (this.projectType !== 'binary') {
                this.logConsole('Building firmware...', 'info');

                const buildFormData = new FormData();

                switch (this.projectType) {
                    case 'esphome':
                        buildFormData.append('yaml_file', mainFile);
                        // Add companion files (HTML, CSS, JS for web_server)
                        for (const f of companionFiles) {
                            buildFormData.append('companion_files', f);
                        }
                        buildFormData.append('board_type', 'esp32');
                        endpoint = '/api/build/esphome';
                        if (companionFiles.length > 0) {
                            this.logConsole(`  Main: ${mainFile.name} + ${companionFiles.length} companion file(s)`, 'info');
                        }
                        break;
                    case 'arduino':
                        buildFormData.append('sketch_file', mainFile);
                        // Add library files (.h, .cpp, .c)
                        for (const f of companionFiles) {
                            buildFormData.append('libraries', f);
                        }
                        buildFormData.append('board_type', 'esp32:esp32:esp32');
                        endpoint = '/api/build/arduino';
                        if (companionFiles.length > 0) {
                            this.logConsole(`  Sketch: ${mainFile.name} + ${companionFiles.length} library file(s)`, 'info');
                        }
                        break;
                    case 'platformio':
                        buildFormData.append('project_zip', mainFile);
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
                const formData = new FormData();
                formData.append('file', mainFile);
                formData.append('board_name', targetBoard);

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

    // ==================== User Management ====================

    async loadUsers() {
        try {
            const data = await this.api('/api/auth/users');
            this.renderUsers(data.users);
        } catch (error) {
            // Silently fail if not on settings tab
        }
    }

    renderUsers(users) {
        const tbody = document.getElementById('users-table-body');
        if (!tbody) return;

        tbody.innerHTML = users.map(user => {
            const created = user.created_at ? new Date(user.created_at).toLocaleDateString() : '-';
            const pwChanged = user.password_changed_at
                ? new Date(user.password_changed_at).toLocaleDateString()
                : 'Never';
            const isSelf = user.username === this.username;
            return `
                <tr class="border-b border-gray-700/50">
                    <td class="py-2">
                        ${user.username}
                        ${isSelf ? '<span class="text-cactus-400 text-xs ml-1">(you)</span>' : ''}
                    </td>
                    <td class="py-2 text-gray-400">${created}</td>
                    <td class="py-2 text-gray-400">${pwChanged}</td>
                    <td class="py-2 text-right">
                        ${!isSelf ? `
                            <button onclick="app.deleteUser('${user.username}')"
                                    class="px-2 py-1 text-xs bg-red-900 hover:bg-red-800 rounded transition-colors">
                                Delete
                            </button>
                        ` : ''}
                    </td>
                </tr>
            `;
        }).join('');
    }

    async registerUser() {
        const username = document.getElementById('reg-username').value;
        const password = document.getElementById('reg-password').value;
        const confirm = document.getElementById('reg-password-confirm').value;
        const errorEl = document.getElementById('reg-error');

        errorEl.classList.add('hidden');

        if (password !== confirm) {
            errorEl.textContent = 'Passwords do not match';
            errorEl.classList.remove('hidden');
            return;
        }

        try {
            await this.api('/api/auth/register', {
                method: 'POST',
                body: JSON.stringify({ username, password }),
            });
            this.showToast(`User "${username}" registered`, 'success');
            document.getElementById('register-user-form').reset();
            document.getElementById('reg-password-strength').classList.add('hidden');
            this.loadUsers();
        } catch (error) {
            errorEl.textContent = error.message;
            errorEl.classList.remove('hidden');
        }
    }

    async changePassword() {
        const oldPassword = document.getElementById('cp-old-password').value;
        const newPassword = document.getElementById('cp-new-password').value;
        const confirmPassword = document.getElementById('cp-new-password-confirm').value;
        const errorEl = document.getElementById('cp-error');

        errorEl.classList.add('hidden');

        if (newPassword !== confirmPassword) {
            errorEl.textContent = 'New passwords do not match';
            errorEl.classList.remove('hidden');
            return;
        }

        try {
            await this.api('/api/auth/change-password', {
                method: 'PUT',
                body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
            });
            this.showToast('Password changed successfully', 'success');
            document.getElementById('change-password-form').reset();
            document.getElementById('cp-password-strength').classList.add('hidden');
            this.loadUsers();
        } catch (error) {
            errorEl.textContent = error.message;
            errorEl.classList.remove('hidden');
        }
    }

    async deleteUser(username) {
        if (!confirm(`Delete user "${username}"? This cannot be undone.`)) return;

        try {
            await this.api(`/api/auth/users/${username}`, { method: 'DELETE' });
            this.showToast(`User "${username}" deleted`, 'success');
            this.loadUsers();
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    showPasswordStrength(password, elementId) {
        const el = document.getElementById(elementId);
        if (!password) {
            el.classList.add('hidden');
            return;
        }

        el.classList.remove('hidden');
        const checks = [
            { test: password.length >= 8, label: '8+ chars' },
            { test: /[A-Z]/.test(password), label: 'Uppercase' },
            { test: /[a-z]/.test(password), label: 'Lowercase' },
            { test: /\d/.test(password), label: 'Digit' },
            { test: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]/.test(password), label: 'Special' },
        ];

        const passed = checks.filter(c => c.test).length;
        const color = passed <= 2 ? 'text-red-400' : passed <= 4 ? 'text-yellow-400' : 'text-cactus-400';

        el.innerHTML = checks.map(c =>
            `<span class="${c.test ? 'text-cactus-400' : 'text-gray-500'}">${c.test ? '&#10003;' : '&#10007;'} ${c.label}</span>`
        ).join(' &middot; ');
        el.className = `text-xs ${color}`;
    }

    // ==================== WebSocket ====================

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

    // ==================== UI Helpers ====================

    showProgress(show) {
        document.getElementById('progress-container').classList.toggle('hidden', !show);
    }

    updateProgress(percent, message) {
        document.getElementById('progress-bar').style.width = `${percent}%`;
        document.getElementById('progress-percent').textContent = `${Math.round(percent)}%`;
        document.getElementById('progress-status').textContent = message;
    }

    logConsole(message, level = 'info') {
        const consoleEl = document.getElementById('console-output');
        const time = new Date().toLocaleTimeString();
        const line = document.createElement('p');
        line.className = `log-${level}`;
        line.textContent = `[${time}] ${message}`;
        consoleEl.appendChild(line);
        consoleEl.scrollTop = consoleEl.scrollHeight;
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
