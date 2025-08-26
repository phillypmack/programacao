"""
Módulo para gerenciamento de conexão com o banco de dados Oracle.
Implementa as operações de consulta e atualização na tabela AD_PLAN.
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.exc import SQLAlchemyError
from config import ORACLE_DATABASE_URI

# Configuração do logger
logger = logging.getLogger(__name__)

class OracleDatabase:
    """
    Classe para gerenciar conexões e operações com o banco de dados Oracle.
    """
    
    def __init__(self):
        """
        Inicializa a conexão com o banco de dados Oracle.
        """
        self.engine = None
        self.connection = None
        
    def connect(self) -> bool:
        """
        Estabelece conexão com o banco de dados Oracle, habilitando o pré-ping
        para manter as conexões vivas.
        """
        try:
            logger.info("Conectando ao banco de dados Oracle...")
            
            # --- MELHORIA ADICIONADA AQUI ---
            # pool_pre_ping=True instrui o SQLAlchemy a verificar a conexão
            # antes de cada operação, evitando erros de timeout.
            self.engine = create_engine(
                ORACLE_DATABASE_URI, 
                echo=False,
                pool_pre_ping=True
            )
            
            self.connection = self.engine.connect()
            logger.info("Conexão com o banco de dados estabelecida com sucesso.")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Erro ao conectar com o banco de dados: {e}")
            return False
        except Exception as e:
            logger.error(f"Erro inesperado ao conectar com o banco: {e}")
            return False
    
    def disconnect(self):
        """
        Fecha a conexão com o banco de dados.
        """
        try:
            if self.connection:
                self.connection.close()
                logger.info("Conexão com o banco de dados fechada.")
            if self.engine:
                self.engine.dispose()
        except Exception as e:
            logger.error(f"Erro ao fechar conexão com o banco: {e}")
    
    def buscar_planejamentos(self, data_planejamento: str, braco: int, 
                           rodada_inicial: int, rodada_final: int) -> List[Dict[str, Any]]:
        """
        Busca os planejamentos pendentes na tabela AD_PLAN com base nos parâmetros fornecidos.
        
        Args:
            data_planejamento (str): Data do planejamento no formato DD/MM/YYYY
            braco (int): Número do braço de produção
            rodada_inicial (int): Rodada inicial do range
            rodada_final (int): Rodada final do range
            
        Returns:
            List[Dict[str, Any]]: Lista de registros encontrados
        """
        if not self.connection:
            logger.error("Conexão com o banco não estabelecida.")
            return []
        
        try:
            # Query SQL conforme especificado no plano de projeto
            query = text("""
                SELECT NUPLAN, CODPROD, QTDPLAN
                FROM AD_PLAN
                WHERE
                    TRUNC(DTINC) = TO_DATE(:data_planejamento, 'YYYY-MM-DD')
                    AND BRACO = :braco
                    AND RODADA BETWEEN :rodada_inicial AND :rodada_final
                    AND IDIPROC IS NULL
                ORDER BY NUPLAN
            """)
            
            # Executa a consulta com os parâmetros
            result = self.connection.execute(query, {
                'data_planejamento': data_planejamento,
                'braco': braco,
                'rodada_inicial': rodada_inicial,
                'rodada_final': rodada_final
            })
            
            # Converte o resultado em lista de dicionários
            registros = []
            for row in result:
                registros.append({
                    'NUPLAN': row[0],
                    'CODPROD': row[1],
                    'QTDPLAN': row[2]
                })
            
            logger.info(f"Encontrados {len(registros)} planejamentos pendentes.")
            return registros
            
        except SQLAlchemyError as e:
            logger.error(f"Erro ao executar consulta SQL: {e}")
            return []
        except Exception as e:
            logger.error(f"Erro inesperado ao buscar planejamentos: {e}")
            return []
    
    def atualizar_idiproc(self, nuplan: int, idiproc: int) -> bool:
        """
        Atualiza o campo IDIPROC na tabela AD_PLAN para um NUPLAN específico.
        
        Args:
            nuplan (int): Número do planejamento (NUPLAN)
            idiproc (int): ID da Ordem de Produção criada
            
        Returns:
            bool: True se a atualização foi bem-sucedida, False caso contrário
        """
        if not self.connection:
            logger.error("Conexão com o banco não estabelecida.")
            return False
        
        try:
            # Query de atualização conforme especificado no plano de projeto
            update_query = text("""
                UPDATE AD_PLAN
                SET IDIPROC = :idiproc_recebido_api
                WHERE NUPLAN = :nuplan_atual
            """)
            
            # Executa a atualização
            result = self.connection.execute(update_query, {
                'idiproc_recebido_api': idiproc,
                'nuplan_atual': nuplan
            })
            
            # Confirma a transação
            self.connection.commit()
            
            if result.rowcount > 0:
                logger.info(f"IDIPROC {idiproc} atualizado com sucesso para NUPLAN {nuplan}.")
                return True
            else:
                logger.warning(f"Nenhum registro foi atualizado para NUPLAN {nuplan}.")
                return False
                
        except SQLAlchemyError as e:
            logger.error(f"Erro ao atualizar IDIPROC: {e}")
            # Rollback em caso de erro
            try:
                self.connection.rollback()
            except:
                pass
            return False
        except Exception as e:
            logger.error(f"Erro inesperado ao atualizar IDIPROC: {e}")
            return False
        
    def gerar_lote_para_ops(self, idiproc_list: List[int], braco: int) -> Optional[int]:
        """
        Chama a procedure STP_GERAR_RODADA_VASAP_EXT para criar um lote unificado,
        e em seguida busca e retorna o NROLOTE gerado.

        Args:
            idiproc_list (List[int]): Lista com os números das OPs (IDIPROC) criadas.
            braco (int): O número do braço de produção que foi programado.

        Returns:
            Optional[int]: O número do lote (NROLOTE) gerado, ou None em caso de falha.
        """
        if not self.connection:
            logger.error("Conexão com o banco não estabelecida para gerar lote.")
            return None
        
        if not idiproc_list:
            logger.warning("Nenhuma OP criada, a geração de lote não será executada.")
            return None

        # CORREÇÃO: Envolve toda a lógica em um único bloco de transação.
        # O 'with' garante que a transação será commitada em caso de sucesso
        # ou sofrerá rollback em caso de erro, deixando a conexão limpa.
        try:
            with self.connection.begin() as trans:
                idiprocs_str = ','.join(map(str, idiproc_list))
                
                logger.info(f"Chamando procedure STP_GERAR_RODADA_VASAP_EXT para as OPs: {idiprocs_str} e Braço: {braco}")

                proc_call = text("BEGIN STP_GERAR_RODADA_VASAP_EXT(:idiprocs, :braco, :mensagem); END;")
                
                self.connection.execute(
                    proc_call, 
                    {"idiprocs": idiprocs_str, "braco": braco, "mensagem": ""}
                )
                
                logger.info("Procedure de geração de lote executada com sucesso.")

                # Após a procedure, busca o NROLOTE gerado DENTRO da mesma transação
                logger.info(f"Buscando o NROLOTE gerado para os IDIPROCs...")
                
                query_lote = text("""
                    SELECT DISTINCT NROLOTE FROM TPRIPROC WHERE IDIPROC IN :idiproc_list AND NROLOTE IS NOT NULL
                """)
                
                result = self.connection.execute(
                    query_lote.bindparams(bindparam('idiproc_list', expanding=True)),
                    {"idiproc_list": idiproc_list}
                )
                nrolote = result.scalar_one_or_none()

                if nrolote:
                    logger.info(f"NROLOTE {nrolote} encontrado com sucesso.")
                    return nrolote
                else:
                    logger.error(f"Não foi possível encontrar o NROLOTE para os IDIPROCs: {idiproc_list}.")
                    # Força o rollback da transação ao levantar uma exceção
                    raise RuntimeError("NROLOTE não encontrado após execução da procedure.")

        except (SQLAlchemyError, RuntimeError) as e:
            logger.error(f"Erro na transação de geração de lote ou busca de NROLOTE: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado ao gerar lote: {e}")
            return None
        
    def atualizar_lote_em_ad_plan(self, nrolote: int, nuplan_list: List[int]) -> bool:
        """
        Atualiza o campo NROLOTE para uma lista de NUPLANs de uma só vez.
        """
        if not self.connection or not nuplan_list: return False
        try:
            logger.info(f"Atualizando NROLOTE={nrolote} para {len(nuplan_list)} registros em AD_PLAN.")
            query = text("UPDATE AD_PLAN SET NROLOTE = :nrolote WHERE NUPLAN IN :nuplan_list")
            
            # Esta função já usa seu próprio bloco de transação, o que é correto.
            # Agora não haverá conflito pois a função anterior limpou a conexão.
            with self.connection.begin() as trans:
                result = self.connection.execute(
                    query.bindparams(bindparam('nuplan_list', expanding=True)),
                    {"nrolote": nrolote, "nuplan_list": nuplan_list}
                )
            
            logger.info(f"{result.rowcount} registros em AD_PLAN atualizados com o novo lote.")
            return result.rowcount > 0
        except SQLAlchemyError as e:
            logger.error(f"Erro ao atualizar NROLOTE em AD_PLAN: {e}")
            return False  
    
    def contar_planejamentos_pendentes(self, data_planejamento: str, braco: int, 
                                      rodada_inicial: int, rodada_final: int) -> int:
        """
        Conta o número total de planejamentos pendentes em um range de rodadas.
        """
        if not self.connection:
            logger.error("Conexão com o banco não estabelecida para contagem.")
            return 0
        
        try:
            query = text("""
                SELECT COUNT(*)
                FROM AD_PLAN
                WHERE
                    TRUNC(DTINC) = TO_DATE(:data_planejamento, 'YYYY-MM-DD')
                    AND BRACO = :braco
                    AND RODADA BETWEEN :rodada_inicial AND :rodada_final
                    AND IDIPROC IS NULL
            """)
            
            result = self.connection.execute(query, {
                'data_planejamento': data_planejamento,
                'braco': braco,
                'rodada_inicial': rodada_inicial,
                'rodada_final': rodada_final
            })
            
            total = result.scalar_one()
            return total
            
        except SQLAlchemyError as e:
            logger.error(f"Erro ao executar contagem SQL: {e}")
            return 0

    def testar_conexao(self) -> bool:
        """
        Testa a conexão com o banco de dados executando uma consulta simples.
        
        Returns:
            bool: True se o teste foi bem-sucedido, False caso contrário
        """
        if not self.connection:
            return False
        
        try:
            result = self.connection.execute(text("SELECT 1 FROM DUAL"))
            row = result.fetchone()
            return row is not None and row[0] == 1
        except Exception as e:
            logger.error(f"Erro no teste de conexão: {e}")
            return False