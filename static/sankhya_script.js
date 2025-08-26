class SankhyaAutomation {
    constructor() {
        this.isProcessing = false;
        this.socket = null; // Soquete será inicializado depois
        this.initializeEventListeners();
        this.connectSocket();
    }

    connectSocket() {
        // Conecta ao servidor WebSocket
        this.socket = io();

        // Ouve por eventos do servidor
        this.socket.on('connect', () => {
            console.log('Conectado ao servidor WebSocket.');
        });

        this.socket.on('log_update', (data) => {
            this.addLogMessage(data.message, data.type);
        });

        this.socket.on('counters_update', (data) => {
            this.updateCounters(data.ops_criadas, data.ops_falhas, data.rodada_atual);
        });

        this.socket.on('progress_bar_update', (data) => {
            this.updateProgress(data.current, data.total);
        });

        this.socket.on('process_finished', () => {
            this.addLogMessage('🎉 Automação concluída!', 'success');
            this.exibirResumoFinal();
            this.isProcessing = false;
            this.showButton('processar-automacao-btn');
        });
    }

    initializeEventListeners() {
        document.getElementById('verificar-conexoes-btn').addEventListener('click', () => this.verificarConexoes());
        document.getElementById('buscar-planejamentos-btn').addEventListener('click', () => this.buscarPlanejamentos());
        document.getElementById('processar-automacao-btn').addEventListener('click', () => this.iniciarAutomacao());
    }

    addLogMessage(message, type = 'info') {
        const logContainer = document.getElementById('sankhya-log');
        const timestamp = new Date().toLocaleTimeString();
        const typeClass = `status-${type}`;
        
        const logEntry = document.createElement('div');
        logEntry.className = `mb-1 ${typeClass}`;
        logEntry.innerHTML = `<span class="text-gray-500">[${timestamp}]</span> ${message}`;
        
        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    clearLog() {
        document.getElementById('sankhya-log').innerHTML = '<p class="text-gray-400">Aguardando início...</p>';
    }

    showButton(id) { document.getElementById(id).classList.remove('hidden'); }
    hideButton(id) { document.getElementById(id).classList.add('hidden'); }
    showSection(id) { document.getElementById(id).classList.remove('hidden'); }
    hideSection(id) { document.getElementById(id).classList.add('hidden'); }

    updateProgress(current, total) {
        const percentage = total > 0 ? Math.round((current / total) * 100) : 0;
        document.getElementById('progress-bar').style.width = `${percentage}%`;
        document.getElementById('progress-text').textContent = `${percentage}%`;
    }

    updateCounters(opsCreated, failures, currentRodada) {
        document.getElementById('ops-criadas').textContent = opsCreated;
        document.getElementById('ops-falhas').textContent = failures;
        document.getElementById('rodada-atual').textContent = currentRodada;
    }

    async verificarConexoes() {
        this.addLogMessage('Resetando estado da aplicação...', 'info');
        try {
            await fetch('/api/sankhya/resetar', { method: 'POST' });
            this.clearLog();
            this.hideButton('buscar-planejamentos-btn');
            this.hideButton('processar-automacao-btn');
            this.hideSection('sankhya-progress-section');
            this.hideSection('sankhya-resumo-section');
            this.updateCounters(0, 0, '-');
            this.updateProgress(0, 0);
            this.addLogMessage('Estado resetado. Verificando conexões...', 'info');

            const response = await fetch('/api/sankhya/verificar_conexoes', { method: 'POST' });
            const result = await response.json();

            if (result.sucesso) {
                this.addLogMessage('✅ ' + result.mensagem, 'success');
                this.showButton('buscar-planejamentos-btn');
            } else {
                this.addLogMessage('❌ ' + result.erro, 'error');
            }
        } catch (error) {
            this.addLogMessage('❌ Erro crítico na verificação: ' + error.message, 'error');
        }
    }

    async buscarPlanejamentos() {
        const dataPlaneamento = document.getElementById('data-planejamento').value;
        const braco = parseInt(document.getElementById('braco-sankhya').value);
        const rodadaInicial = parseInt(document.getElementById('rodada-inicial').value);
        const rodadaFinal = parseInt(document.getElementById('rodada-final').value);

        if (!dataPlaneamento || rodadaInicial > rodadaFinal) {
            this.addLogMessage('❌ Verifique os parâmetros (data e rodadas).', 'error');
            return;
        }

        this.addLogMessage(`Buscando planejamentos...`, 'info');
        try {
            const response = await fetch('/api/sankhya/buscar_planejamentos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data_planejamento: dataPlaneamento, braco, rodada_inicial: rodadaInicial, rodada_final: rodadaFinal })
            });
            const result = await response.json();

            if (result.sucesso) {
                if (result.total > 0) {
                    this.addLogMessage(`✅ Encontrados ${result.total} planejamentos pendentes.`, 'success');
                    this.showButton('processar-automacao-btn');
                } else {
                    this.addLogMessage('⚠️ Nenhum planejamento pendente encontrado.', 'warning');
                    this.hideButton('processar-automacao-btn');
                }
            } else {
                this.addLogMessage('❌ ' + result.erro, 'error');
            }
        } catch (error) {
            this.addLogMessage('❌ Erro ao buscar planejamentos: ' + error.message, 'error');
        }
    }

    async iniciarAutomacao() {
        if (this.isProcessing) {
            this.addLogMessage('⚠️ Automação já está em andamento.', 'warning');
            return;
        }

        this.isProcessing = true;
        this.hideButton('processar-automacao-btn');
        this.showSection('sankhya-progress-section');
        this.hideSection('sankhya-resumo-section'); // Esconde resumo antigo
        this.addLogMessage('🚀 Enviando comando para iniciar automação...', 'info');

        const dataPlaneamento = document.getElementById('data-planejamento').value;
        const braco = parseInt(document.getElementById('braco-sankhya').value);
        const rodadaInicial = parseInt(document.getElementById('rodada-inicial').value);
        const rodadaFinal = parseInt(document.getElementById('rodada-final').value);

        try {
            // Envia um único comando para o backend iniciar todo o processo
            const response = await fetch('/api/sankhya/iniciar_automacao_stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data_planejamento: dataPlaneamento, braco, rodada_inicial: rodadaInicial, rodada_final: rodadaFinal })
            });

            const result = await response.json();
            if (!result.sucesso) {
                this.addLogMessage(`❌ Falha ao iniciar automação: ${result.mensagem}`, 'error');
                this.isProcessing = false;
                this.showButton('processar-automacao-btn');
            }
            // Se sucesso, o frontend agora apenas espera por eventos WebSocket
        } catch (error) {
            this.addLogMessage('❌ Erro ao enviar comando de início: ' + error.message, 'error');
            this.isProcessing = false;
            this.showButton('processar-automacao-btn');
        }
    }

    async exibirResumoFinal() {
        // O método de exibir resumo permanece o mesmo
        try {
            const response = await fetch('/api/sankhya/resumo');
            const resumo = await response.json();
            this.showSection('sankhya-resumo-section');
            const resumoContent = document.getElementById('resumo-content');
            resumoContent.innerHTML = `
                <div class="grid md:grid-cols-2 gap-6">
                    <div class="bg-gray-700 p-4 rounded-lg">
                        <h3 class="text-lg font-semibold text-green-400 mb-3"><i class="fas fa-check-circle mr-2"></i>Sucessos (${resumo.total_ops_criadas})</h3>
                        <div class="max-h-40 overflow-y-auto">${resumo.ops_criadas_sucesso.length > 0 ? resumo.ops_criadas_sucesso.map(op => `<div class="text-sm text-gray-300 mb-1">NUPLAN: ${op.nuplan} → OP: ${op.idiproc}</div>`).join('') : '<div class="text-sm text-gray-400">Nenhuma OP criada</div>'}</div>
                    </div>
                    <div class="bg-gray-700 p-4 rounded-lg">
                        <h3 class="text-lg font-semibold text-red-400 mb-3"><i class="fas fa-exclamation-triangle mr-2"></i>Falhas (${resumo.total_falhas})</h3>
                        <div class="max-h-40 overflow-y-auto">${resumo.detalhes_falhas.length > 0 ? resumo.detalhes_falhas.map(f => `<div class="text-sm text-gray-300 mb-2"><div class="font-medium">NUPLAN: ${f.nuplan}</div><div class="text-red-300 text-xs">${f.erro}</div></div>`).join('') : '<div class="text-sm text-gray-400">Nenhuma falha</div>'}</div>
                    </div>
                </div>`;
        } catch (error) {
            this.addLogMessage('❌ Erro ao carregar resumo: ' + error.message, 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const sankhyaApp = new SankhyaAutomation();
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('data-planejamento').value = today;
});