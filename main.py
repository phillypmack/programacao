import os
import sys
import logging
import json
from typing import Dict, Any, Optional
from threading import Thread
from flask import Flask, send_from_directory, request, jsonify
from flask_socketio import SocketIO

# Importações do sankhya_op_automation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'sankhya_automation'))
from database import OracleDatabase
from sankhya_api import SankhyaAPI

# --- INICIALIZAÇÃO DO FLASK E SOCKET.IO ---
app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a-fallback-secret-key')
# Habilita CORS para permitir conexões de qualquer origem (útil para desenvolvimento)
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # Garante que o arquivo de log seja escrito em UTF-8
        logging.FileHandler('unified_app.log', encoding='utf-8'),
        # Garante que a saída do console também use UTF-8
        logging.StreamHandler(sys.stdout)
    ]
)
# Força o encoding do stdout para UTF-8 em ambientes como o Windows
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except TypeError:
        # Em alguns ambientes (como o IDLE), reconfigure não é suportado.
        # Nesses casos, o erro de encode pode persistir, mas não quebrará a aplicação.
        pass
logger = logging.getLogger(__name__)

class SankhyaAutomationAPI:
    def __init__(self, socketio_instance):
        self.socketio = socketio_instance
        self.db: Optional[OracleDatabase] = None
        self.api: Optional[SankhyaAPI] = None
        self.total_ops_criadas = 0
        self.total_falhas = 0
        self.ops_criadas_sucesso = []
        self.detalhes_falhas = []

    def _emit_log(self, message, log_type='info'):
        """Envia uma mensagem de log para o frontend via WebSocket."""
        self.socketio.emit('log_update', {'message': message, 'type': log_type})
        # Também registra no log do servidor
        if log_type == 'error':
            logger.error(message)
        else:
            logger.info(message)

    def _emit_counters(self, rodada_atual):
        """Envia a atualização dos contadores para o frontend."""
        self.socketio.emit('counters_update', {
            'ops_criadas': self.total_ops_criadas,
            'ops_falhas': self.total_falhas,
            'rodada_atual': rodada_atual
        })

    def verificar_conexoes(self) -> Dict[str, Any]:
        try:
            if not self.db: self.db = OracleDatabase()
            if not self.api: self.api = SankhyaAPI()
            
            if not self.db.connect() or not self.db.testar_conexao():
                return {"sucesso": False, "erro": "Falha na conexão com o banco Oracle"}
            
            if not self.api.testar_conexao():
                self.db.disconnect()
                return {"sucesso": False, "erro": "Falha na conexão com a API Sankhya"}
            
            return {"sucesso": True, "mensagem": "Conexões estabelecidas com sucesso"}
        except Exception as e:
            logger.error(f"Erro ao verificar conexões: {e}", exc_info=True)
            return {"sucesso": False, "erro": str(e)}

    def buscar_planejamentos(self, data_planejamento: str, braco: int, rodada_inicial: int, rodada_final: int) -> Dict[str, Any]:
        try:
            if not self.db: return {"sucesso": False, "erro": "Conexão com banco não estabelecida"}
            total = self.db.contar_planejamentos_pendentes(data_planejamento, braco, rodada_inicial, rodada_final)
            return {"sucesso": True, "total": total}
        except Exception as e:
            logger.error(f"Erro ao buscar planejamentos: {e}", exc_info=True)
            return {"sucesso": False, "erro": str(e)}

    def executar_automacao_completa(self, data_planejamento: str, braco: int, rodada_inicial: int, rodada_final: int):
        """
        Executa o processo completo, do início ao fim, emitindo eventos WebSocket.
        Este método é projetado para rodar em uma thread de background.
        """
        global processo_em_andamento
        try:
            # --- CORREÇÃO 1: Calcular o total de registros, não de rodadas ---
            total_registros_a_processar = self.db.contar_planejamentos_pendentes(data_planejamento, braco, rodada_inicial, rodada_final)
            registros_processados = 0
            self._emit_log(f"Total de {total_registros_a_processar} planejamentos a serem processados.", 'info')
            
            # Inicializa a barra de progresso no frontend
            self.socketio.emit('progress_bar_update', {'current': 0, 'total': total_registros_a_processar})

            for rodada in range(rodada_inicial, rodada_final + 1):
                self._emit_log(f"--- Iniciando processamento da Rodada: {rodada} ---", 'info')
                self._emit_counters(rodada)
                
                if not self.api.autenticar():
                    self._emit_log(f"Falha ao autenticar para a Rodada {rodada}. Abortando.", 'error')
                    break

                registros = self.db.buscar_planejamentos(data_planejamento, braco, rodada, rodada)
                if not registros:
                    self._emit_log(f"Nenhum planejamento pendente para a Rodada {rodada}.", 'warning')
                    continue

                idiprocs_desta_rodada = []
                nuplans_desta_rodada = []

                for reg_idx, registro in enumerate(registros, 1):
                    self._emit_log(f"  [{reg_idx}/{len(registros)}-{rodada}] Processando NUPLAN: {registro['NUPLAN']}...", 'info')
                    try:
                        dados_produto_api = {"CODPRODPA": registro['CODPROD'], "IDPROC": 51, "CODPLP": 1, "TAMLOTE": registro['QTDPLAN']}
                        sucesso, idiproc, mensagem = self.api.criar_ordem_producao(dados_produto_api)

                        if sucesso and idiproc:
                            if self.db.atualizar_idiproc(registro['NUPLAN'], idiproc):
                                self._emit_log(f"    ✅ OP {idiproc} criada para NUPLAN {registro['NUPLAN']}.", 'success')
                                self.total_ops_criadas += 1
                                self.ops_criadas_sucesso.append({"nuplan": registro['NUPLAN'], "idiproc": idiproc})
                                idiprocs_desta_rodada.append(idiproc)
                                nuplans_desta_rodada.append(registro['NUPLAN'])
                            else:
                                self.total_falhas += 1
                                erro_msg = f"OP {idiproc} criada, mas FALHA ao atualizar banco."
                                self._emit_log(f"    ❌ {erro_msg}", 'error')
                                self.detalhes_falhas.append({"nuplan": registro['NUPLAN'], "erro": erro_msg})
                        else:
                            self.total_falhas += 1
                            erro_msg = f"Erro ao criar OP: {mensagem}"
                            self._emit_log(f"    ❌ {erro_msg}", 'error')
                            self.detalhes_falhas.append({"nuplan": registro['NUPLAN'], "erro": erro_msg})
                        
                        self._emit_counters(rodada)
                    except Exception as e:
                        self.total_falhas += 1
                        erro_msg = f"Erro inesperado no NUPLAN {registro['NUPLAN']}: {e}"
                        self._emit_log(f"    ❌ {erro_msg}", 'error')
                        self.detalhes_falhas.append({"nuplan": registro['NUPLAN'], "erro": erro_msg})
                    finally:
                        # --- CORREÇÃO 2: Atualizar a barra a cada registro processado ---
                        registros_processados += 1
                        self.socketio.emit('progress_bar_update', {'current': registros_processados, 'total': total_registros_a_processar})
                
                if idiprocs_desta_rodada:
                    nro_lote = self.db.gerar_lote_para_ops(idiprocs_desta_rodada, braco)
                    if nro_lote:
                        self._emit_log(f"Lote {nro_lote} gerado para a Rodada {rodada}.", 'success')
                        if self.db.atualizar_lote_em_ad_plan(nro_lote, nuplans_desta_rodada):
                            self._emit_log(f"AD_PLAN atualizada com o lote {nro_lote}.", 'success')
                        else:
                            self._emit_log(f"FALHA ao atualizar AD_PLAN com o lote.", 'error')
                    else:
                        self._emit_log(f"FALHA ao gerar lote para a Rodada {rodada}.", 'error')
                
                # --- CORREÇÃO 3: Remover a atualização antiga e incorreta ---
                # self.socketio.emit('progress_bar_update', {'current': i + 1, 'total': total_rodadas})

        except Exception as e:
            self._emit_log(f"Erro crítico durante a automação: {e}", 'error')
            logger.error("Erro crítico na thread de automação", exc_info=True)
        finally:
            self.finalizar_conexoes()
            self._emit_log("🎉 Automação concluída!", 'success')
            self.socketio.emit('process_finished', {})
            processo_em_andamento = False
            logger.info("Flag 'processo_em_andamento' redefinida para False.")

    def finalizar_conexoes(self):
        try:
            if self.api: self.api.logout()
            if self.db and self.db.connection: self.db.disconnect()
        except Exception as e:
            logger.error(f"Erro ao finalizar conexões: {e}")

    def obter_resumo(self):
        return {"total_ops_criadas": self.total_ops_criadas, "total_falhas": self.total_falhas,
                "ops_criadas_sucesso": self.ops_criadas_sucesso, "detalhes_falhas": self.detalhes_falhas}

# --- GERENCIAMENTO DE ESTADO E ROTAS DA API ---
sankhya_automation: Optional[SankhyaAutomationAPI] = None
processo_em_andamento = False

@app.route('/api/sankhya/resetar', methods=['POST'])
def resetar_estado():
    global sankhya_automation
    sankhya_automation = SankhyaAutomationAPI(socketio)
    logger.info("Estado da automação Sankhya foi resetado.")
    return jsonify({"sucesso": True, "mensagem": "Estado resetado com sucesso."})

@app.route('/api/sankhya/verificar_conexoes', methods=['POST'])
def verificar_conexoes():
    if not sankhya_automation: return jsonify({"sucesso": False, "erro": "Estado não inicializado. Chame /resetar primeiro."})
    return jsonify(sankhya_automation.verificar_conexoes())

@app.route('/api/sankhya/buscar_planejamentos', methods=['POST'])
def buscar_planejamentos():
    if not sankhya_automation: return jsonify({"sucesso": False, "erro": "Estado não inicializado."})
    data = request.json
    return jsonify(sankhya_automation.buscar_planejamentos(data['data_planejamento'], data['braco'], data['rodada_inicial'], data['rodada_final']))

@app.route('/api/sankhya/iniciar_automacao_stream', methods=['POST'])
def iniciar_automacao_stream():
    global processo_em_andamento
    if processo_em_andamento:
        return jsonify({"sucesso": False, "mensagem": "Um processo já está em andamento."}), 409
    if not sankhya_automation:
        return jsonify({"sucesso": False, "erro": "Estado não inicializado."}), 500

    data = request.json
    processo_em_andamento = True
    
    thread = Thread(target=sankhya_automation.executar_automacao_completa, args=(
        data['data_planejamento'], data['braco'], data['rodada_inicial'], data['rodada_final']
    ))
    thread.daemon = True
    thread.start()
    
    return jsonify({"sucesso": True, "mensagem": "Processo de automação iniciado em segundo plano."}), 202

@app.route('/api/sankhya/resumo', methods=['GET'])
def obter_resumo():
    if not sankhya_automation: return jsonify({"sucesso": False, "erro": "Estado não inicializado."})
    return jsonify(sankhya_automation.obter_resumo())

# Rotas para servir o frontend
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    # Usa socketio.run() para iniciar o servidor
    socketio.run(app, host='0.0.0.0', port=5001, debug=False, allow_unsafe_werkzeug=True)