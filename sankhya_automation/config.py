"""
Arquivo de configuração para a aplicação de automação de Ordens de Produção Sankhya.
Este arquivo contém as configurações de conexão com o banco Oracle e API Sankhya.
"""

import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env se existir
load_dotenv()

# Configurações do Banco de Dados Oracle
ORACLE_CONFIG = {
    'host': os.getenv('ORACLE_HOST'),
    'port': os.getenv('ORACLE_PORT'),
    'service_name': os.getenv('ORACLE_SERVICE'),
    'username': os.getenv('ORACLE_USER'),
    'password': os.getenv('ORACLE_PASSWORD')
}

# String de conexão Oracle
ORACLE_DATABASE_URI = f"oracle+oracledb://{ORACLE_CONFIG['username']}:{ORACLE_CONFIG['password']}@{ORACLE_CONFIG['host']}:{ORACLE_CONFIG['port']}/{ORACLE_CONFIG['service_name']}"

# Configurações da API Sankhya
SANKHYA_CONFIG = {
    'base_url': os.getenv('SANKHYA_BASE_URL'),
    'login_url': os.getenv('SANKHYA_LOGIN_URL'),
    'gateway_url': os.getenv('SANKHYA_GATEWAY_URL'),
    'app_key': os.getenv('SANKHYA_APP_KEY'),
    'client_token': os.getenv('SANKHYA_CLIENT_TOKEN'),
    'username': os.getenv('SANKHYA_USERNAME'),
    'password': os.getenv('SANKHYA_PASSWORD'),
    'mge_session': os.getenv('SANKHYA_MGE_SESSION')
}

# Configurações da aplicação
APP_CONFIG = {
    'debug': os.getenv('DEBUG', 'False').lower() == 'true',
    'log_level': os.getenv('LOG_LEVEL', 'INFO'),
    'timeout': int(os.getenv('REQUEST_TIMEOUT', '60'))
}
