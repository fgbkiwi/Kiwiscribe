# Transcrição para 4 canais de áudio com AssemblyAI e pós-processamento com Claude, OpenAI e Gemini
import sys
import os
import json
import requests
import platform
from urllib.parse import urlparse
import assemblyai as aai
import threading
import re
import subprocess
import tempfile
from datetime import datetime, timedelta
import anthropic
import time
import PyPDF2
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit,
                             QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
                             QDialog, QVBoxLayout as QVBoxLayoutDialog, QRadioButton,
                             QMessageBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QBrush, QColor
import openai
from openai import OpenAI
import google.genai as genai # Import simplificado para Gemini

# --- Configuração Inicial Gemini ---
# (Nova configuração para google-genai - usa GOOGLE_API_KEY automaticamente)
if os.getenv('GOOGLE_API_KEY'):
    print("GOOGLE_API_KEY detectada no ambiente.")
elif os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
    cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if not os.path.exists(cred_path):
        print(f"AVISO: O arquivo de credenciais em GOOGLE_APPLICATION_CREDENTIALS ('{cred_path}') não foi encontrado.")
    else:
        print(f"GOOGLE_APPLICATION_CREDENTIALS detectada: {cred_path}")
else:
    print("AVISO: Nenhuma credencial Google (API Key ou Application Credentials) encontrada no ambiente. Gemini não funcionará.")

# --- Funções Auxiliares ---
def get_download_dir():
    """Retorna o diretório de downloads padrão do sistema operacional."""
    system = platform.system()
    try:
        if system == 'Windows':
            import winreg
            subkey = r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
            value_name = '{374DE290-123F-4565-9164-39C4925E467B}' # GUID para Downloads
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as key:
                path = winreg.QueryValueEx(key, value_name)[0]
            # Expande variáveis de ambiente como %USERPROFILE%
            return os.path.expandvars(path)
        elif system == 'Darwin': # macOS
            return os.path.expanduser('~/Downloads')
        elif system == 'Linux':
             # Tenta usar xdg-user-dir se disponível (padrão Freedesktop)
            result = subprocess.run(['xdg-user-dir', 'DOWNLOAD'], capture_output=True, text=True, check=False)
            if result.returncode == 0 and result.stdout.strip():
                path = result.stdout.strip()
                if os.path.isdir(path):
                    return path
             # Fallback para ~/Downloads se xdg-user-dir falhar
            return os.path.expanduser('~/Downloads')
    except Exception as e:
        print(f"Erro ao obter diretório de downloads: {e}. Usando diretório do usuário.")
        # Fallback mais seguro para o diretório home do usuário
        return os.path.expanduser('~')

    # Fallback final para o diretório de trabalho atual se tudo falhar
    return os.getcwd()

# Arquivo para armazenar as API Keys
CONFIG_FILE = os.path.join(os.path.expanduser('~'), '.transcription_config.json')

def load_api_keys():
    """Carrega as chaves de API do arquivo de configuração JSON."""
    keys = {'assembly_ai': '', 'claude': '', 'openai': '', 'gemini': ''} # Padrão
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded_keys = json.load(f)
                # Atualiza o dicionário padrão apenas com as chaves encontradas no arquivo
                keys.update(loaded_keys)
        except (json.JSONDecodeError, IOError) as e:
             print(f"Erro ao carregar arquivo de configuração ({CONFIG_FILE}): {e}. Usando valores padrão.")
    return keys

def save_api_keys(assembly_key, claude_key, openai_key, gemini_key):
    """Salva as chaves de API no arquivo de configuração JSON."""
    config = {
        'assembly_ai': assembly_key,
        'claude': claude_key,
        'openai': openai_key,
        'gemini': gemini_key
    }
    try:
        # Cria o diretório pai se não existir (para o caso de ser a primeira vez)
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4) # Adiciona indentação para legibilidade
    except IOError as e:
        print(f"Erro ao salvar as chaves de API em {CONFIG_FILE}: {e}")

def ms_to_formatted_time(milliseconds):
    """Converte milissegundos para o formato HH:MM:SS."""
    if not isinstance(milliseconds, (int, float)) or milliseconds < 0:
        return "00:00:00" # Retorna um valor padrão para entradas inválidas
    total_seconds = int(milliseconds / 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def get_audio_duration_from_path(file_path):
    """Obtém a duração do áudio de um arquivo local usando ffprobe, com fallback para estimativa."""
    # Prioriza ffprobe se estiver disponível
    try:
        # Verifica se ffprobe está no PATH ou especifica o caminho completo se necessário
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', file_path], # Saída direta da duração
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True # Lança exceção se ffprobe retornar erro
        )
        duration_seconds = float(result.stdout.strip())
        return int(duration_seconds * 1000) # Retorna em milissegundos
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        print(f"ffprobe falhou para '{os.path.basename(file_path)}' ({e}), tentando estimativa por tamanho.")
        # Fallback para estimativa baseada no tamanho do arquivo se ffprobe falhar
        try:
            file_size = os.path.getsize(file_path)
            # Estimativa MUITO grosseira (ex: ~1MB/minuto para MP3 128kbps)
            # Ajuste essa taxa (bytes_per_millisecond) conforme necessário
            bytes_per_second_estimate = 16000 # Estimativa (ex: 128kbps / 8 = 16kB/s)
            if bytes_per_second_estimate > 0:
                 estimated_duration_sec = file_size / bytes_per_second_estimate
                 print(f"Estimativa por tamanho ({file_size} bytes): {int(estimated_duration_sec * 1000)} ms")
                 return int(estimated_duration_sec * 1000)
            else:
                 return 300000 # Retorna 5 minutos como padrão se a estimativa falhar
        except OSError as size_error:
             print(f"Erro ao obter tamanho do arquivo: {size_error}")
             return 300000 # 5 minutos como padrão se não conseguir ler o tamanho

def get_audio_duration_from_url(url):
    """Obtém a duração estimada de um áudio a partir de um URL."""
    try:
        # Primeiro tenta obter o tamanho via HEAD request (mais eficiente)
        response_head = requests.head(url, allow_redirects=True, timeout=10)
        response_head.raise_for_status() # Verifica se houve erro HTTP
        file_size = int(response_head.headers.get('content-length', 0))

        if file_size > 0:
            # Estimativa grosseira baseada no tamanho (similar ao get_audio_duration_from_path)
            bytes_per_second_estimate = 16000 # Estimativa (ex: 128kbps / 8 = 16kB/s)
            if bytes_per_second_estimate > 0:
                 estimated_duration_sec = file_size / bytes_per_second_estimate
                 print(f"Estimativa de duração URL baseada no tamanho ({file_size} bytes): {int(estimated_duration_sec * 1000)} ms")
                 return int(estimated_duration_sec * 1000)

        # Se o tamanho não ajudar, *não* baixa o arquivo inteiro (pode ser muito grande)
        # Poderia baixar um pedaço e tentar ffprobe, mas aumenta a complexidade e tempo.
        print("Tamanho do URL não disponível ou zero. Retornando duração padrão.")
        return 300000 # Padrão de 5 minutos se não houver Content-Length

    except requests.exceptions.RequestException as e:
        print(f"Erro ao acessar URL ({e}), retornando duração padrão.")
        return 300000 # Padrão de 5 minutos
    except Exception as e:
        print(f"Erro inesperado ao obter duração do URL ({e}), retornando duração padrão.")
        return 300000 # Padrão de 5 minutos

def get_estimated_transcription_time(recording_duration_ms):
    """Estima o horário de conclusão da transcrição."""
    # Estimativa: AssemblyAI leva ~1/4 do tempo do áudio. Whisper/Gemini podem variar.
    # Usa um fator conservador (ex: 0.6) para abranger todos e adiciona margem.
    factor = 0.6
    estimated_processing_duration = timedelta(milliseconds=recording_duration_ms * factor)
    # Adiciona um tempo base fixo para inicialização, upload, etc. (ex: 2 minutos)
    base_time = timedelta(minutes=2)
    completion_time = datetime.now() + estimated_processing_duration + base_time
    return completion_time.strftime("%Hh%M")

def get_audio_channels(file_path):
    """Detecta o número de canais em um arquivo de áudio usando ffprobe."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'a:0', 
             '-show_entries', 'stream=channels', '-of', 'default=noprint_wrappers=1:nokey=1', 
             file_path],
            capture_output=True, text=True, check=True
        )
        return int(result.stdout.strip())
    except:
        return 1  # Assume mono se falhar

def extract_info_from_ata(ata_path):
    """Extrai informações relevantes (Juiz, partes, advogados, testemunhas) de um arquivo de ata (.txt ou .pdf)."""
    try:
        text = ""
        if not os.path.exists(ata_path):
            return "Erro: Arquivo da ata não encontrado."
        if not ata_path.lower().endswith(('.pdf', '.txt')):
             return "Erro: Formato de arquivo da ata não suportado (use .pdf ou .txt)."
        
        if ata_path.lower().endswith('.pdf'):
            try:
                with open(ata_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n"
            except Exception as e:
                return f"Erro ao ler PDF: {e}"
        else:  # .txt
            try:
                with open(ata_path, 'r', encoding='utf-8') as file:
                    text = file.read()
            except Exception as e:
                return f"Erro ao ler arquivo de texto: {e}"
        
        if not text.strip():
            return "Erro: Arquivo da ata está vazio ou não foi possível extrair texto."
        
        return text
    except Exception as e:
        return f"Erro inesperado ao processar ata: {e}"

def parse_depoentes_from_ata(ata_text):
    """Extrai da ata a sequência de depoentes em ordem de depoimento."""
    depoentes = []
    
    try:
        # Buscar informações das partes presentes
        reclamante_nome = ""
        reclamado_nome = ""
        
        # Extrair nome do reclamante
        reclamante_match = re.search(r'RECLAMANTE:\s*([^A-Z]+?)(?:\s+ADVOGADO|$)', ata_text, re.IGNORECASE)
        if reclamante_match:
            reclamante_nome = reclamante_match.group(1).strip()
        
        # Extrair nome do reclamado/preposto
        reclamado_match = re.search(r'representado\(a\)\s+pelo\(a\)\s+preposto\(a\)\s+([^,]+)', ata_text, re.IGNORECASE)
        if reclamado_match:
            reclamado_nome = reclamado_match.group(1).strip()
        
        # 1. Verificar depoimento do reclamante
        reclamante_dep_match = re.search(r'Depoimento\s+pessoal\s+do\(a\)\s+autor\(a\)\s+(gravado|dispensado)', ata_text, re.IGNORECASE)
        if reclamante_dep_match and 'gravado' in reclamante_dep_match.group(1).lower():
            if reclamante_nome:
                depoentes.append(("Reclamante", reclamante_nome))
            else:
                depoentes.append(("Reclamante", "Reclamante"))
        
        # 2. Verificar depoimento do reclamado
        reclamado_dep_match = re.search(r'Depoimento\s+pessoal\s+do\s+representante\s+do\(a\)\s+reclamado\(a\)\s+(gravado|dispensado)', ata_text, re.IGNORECASE)
        if reclamado_dep_match and 'gravado' in reclamado_dep_match.group(1).lower():
            if reclamado_nome:
                depoentes.append(("Representante da Reclamada", reclamado_nome))
            else:
                depoentes.append(("Representante da Reclamada", "Representante da Reclamada"))
        
        # 3. Buscar testemunhas do reclamante (ordem: 1ª, 2ª, etc.)
        testemunhas_reclamante = []
        for match in re.finditer(r'(\d+ª?\s*testemunha\s+do\(a\)\s+reclamante[^:]*?):\s*([^,\n]+)', ata_text, re.IGNORECASE):
            tipo = match.group(1).strip()
            nome = match.group(2).strip()
            if nome:
                testemunhas_reclamante.append((tipo, nome))
        
        # Ordenar testemunhas do reclamante por número
        testemunhas_reclamante.sort(key=lambda x: int(re.search(r'(\d+)', x[0]).group(1)) if re.search(r'(\d+)', x[0]) else 0)
        depoentes.extend(testemunhas_reclamante)
        
        # 4. Buscar testemunhas do reclamado (ordem: 1ª, 2ª, etc.)
        testemunhas_reclamado = []
        for match in re.finditer(r'(\d+ª?\s*testemunha\s+do\(a\)\s+reclamado[^:]*?):\s*([^,\n]+)', ata_text, re.IGNORECASE):
            tipo = match.group(1).strip()
            nome = match.group(2).strip()
            if nome:
                testemunhas_reclamado.append((tipo, nome))
        
        # Ordenar testemunhas do reclamado por número
        testemunhas_reclamado.sort(key=lambda x: int(re.search(r'(\d+)', x[0]).group(1)) if re.search(r'(\d+)', x[0]) else 0)
        depoentes.extend(testemunhas_reclamado)
        
        return depoentes
        
    except Exception as e:
        print(f"Erro ao extrair depoentes da ata: {e}")
        return []

def format_ata_info(ata_path):
    """Formata as informações da ata para uso no prompt de pós-processamento."""
    ata_text = extract_info_from_ata(ata_path)
    
    if ata_text.startswith("Erro:"):
        return f"⚠️ AVISO: {ata_text}"
    
    # Extrair informações específicas usando regex
    info = {}
    
    # Buscar Juiz
    juiz_match = re.search(r'Juiz\(a\)[:\s]+([^\n]+)', ata_text, re.IGNORECASE)
    if juiz_match:
        info['juiz'] = juiz_match.group(1).strip()
    
    # Buscar partes presentes
    presente_match = re.search(r'Presente\s+a\s+parte[:\s]*([^.]*)', ata_text, re.IGNORECASE | re.DOTALL)
    if presente_match:
        info['presentes'] = presente_match.group(1).strip()
    
    # Buscar advogados
    advogados = re.findall(r'Advogado\(a\)[:\s]+([^\n,]+)', ata_text, re.IGNORECASE)
    if advogados:
        info['advogados'] = advogados
    
    # Buscar testemunhas
    testemunhas = re.findall(r'(\d+ª?\s*testemunha[^:\n]+)', ata_text, re.IGNORECASE)
    if testemunhas:
        info['testemunhas'] = testemunhas
    
    # Formatar saída
    formatted = "**INFORMAÇÕES DA ATA:**\n\n"
    
    if 'juiz' in info:
        formatted += f"**Juiz(a):** {info['juiz']}\n"
    
    if 'presentes' in info:
        formatted += f"**Presentes:** {info['presentes']}\n"
    
    if 'advogados' in info:
        formatted += f"**Advogados:** {', '.join(info['advogados'])}\n"
    
    if 'testemunhas' in info:
        formatted += f"**Testemunhas:** {', '.join(info['testemunhas'])}\n"
    
    # Adicionar sequência de depoentes
    depoentes = parse_depoentes_from_ata(ata_text)
    if depoentes:
        formatted += f"\n**SEQUÊNCIA DE DEPOENTES:**\n"
        for i, (tipo, nome) in enumerate(depoentes, 1):
            formatted += f"{i}. {tipo}: {nome}\n"
    
    return formatted

def create_post_processing_prompt(ata_info_formatted, transcript_text_chunk=None):
    """Cria o prompt padrão para os modelos de LLM realizarem o pós-processamento."""
    # Verifica se a formatação da ata resultou em erro ou aviso
    if ata_info_formatted.startswith("⚠️ AVISO:"):
        ata_section = f"**INFORMAÇÕES DA ATA:**\n{ata_info_formatted}\n"
    else:
        ata_section = ata_info_formatted

    labels = """
**Rótulos a serem usados para identificar cada interlocutor:**
- Juiz: 
- Reclamante: 
- Advogado do Reclamante: 
- Representante da Reclamada: 
- Advogado da Reclamada: 
- (Se houver mais de uma Reclamada):
  - Representante da 1ª Reclamada:
  - Advogado da 1ª Reclamada:
  - Representante da 2ª Reclamada:
  - Advogado da 2ª Reclamada:
- (Se houver mais Reclamadas, siga o padrão acima)
- 1ª Testemunha do Reclamante: 
- 2ª Testemunha do Reclamante: (e assim por diante)
- 1ª Testemunha da Reclamada: 
- 2ª Testemunha da Reclamada: (e assim por diante)
- Interlocutor Não Identificado: (Use apenas se for impossível determinar quem falou)
"""

    prompt = f"""
Você é um assistente especialista em Direito Processual do Trabalho brasileiro, com foco em transcrições de audiências trabalhistas. Sua tarefa é pós-processar uma transcrição de audiência judicial, corrigindo a identificação dos interlocutores e mantendo a fidelidade do conteúdo.

A transcrição foi realizada com gravação multicanal (4 canais), com identificação automática por canal:
- Canal 1: Juiz
- Canal 2: Advogado do Reclamante  
- Canal 3: Advogado do Reclamado
- Canal 4: Depoente (sequência conforme ata)

Sua tarefa é apenas refinar o texto, corrigir erros de transcrição e manter a 
formatação. A identificação dos interlocutores já está correta.

{ata_section}

**ESTRUTURA TÍPICA DE UMA AUDIÊNCIA TRABALHISTA (BASEADO NO EXEMPLO FORNECIDO):**

1. **ABERTURA DA AUDIÊNCIA:**
   - Juiz abre a audiência e apregoadas as partes
   - Registro dos presentes (reclamante, reclamada, advogados, acadêmicos)

2. **CONCILIAÇÃO:**
   - Tentativa de conciliação (pode ser rejeitada)

3. **DEPOIMENTOS DAS PARTES:**
   - Depoimento pessoal do reclamante (se gravado)
   - Depoimento pessoal do representante da reclamada (se gravado)

4. **DEPOIMENTOS DAS TESTEMUNHAS:**
   - 1ª testemunha do reclamante
   - 2ª testemunha do reclamante
   - 1ª testemunha da reclamada
   - 2ª testemunha da reclamada

**REGRAS PROCESSUAIS CRÍTICAS PARA IDENTIFICAÇÃO CORRETA:**

1. **IDENTIFICAÇÃO DAS PARTES PRESENTES:**
   * **CRÍTICO**: A primeira folha da ata (folha de rosto) contém informações cadastrais que podem estar desatualizadas
   * **CRÍTICO**: Use APENAS as informações da seção "Presente a parte..." que aparece após "ATA DE AUDIÊNCIA"
   * **CRÍTICO**: Identifique corretamente:
     - Reclamante e seu advogado
     - Reclamada (pessoa jurídica) e seu representante/preposto
     - Advogado(s) da reclamada
     - Acadêmicos (quando presentes)

2. **DEPOIMENTO DAS PARTES:**
   * **CRÍTICO**: Verifique ATENTAMENTE na ata se o depoimento foi "gravado" ou "dispensado"
   * Se constar "Depoimento pessoal do(a) autor(a) dispensado" ou "Depoimento pessoal do representante do(a) reclamado(a) dispensado", essa parte NÃO prestou depoimento
   * Apenas considere que uma parte prestou depoimento se constar "gravado"
   * **REGRAS CRÍTICAS SOBRE QUEM PODE FAZER PERGUNTAS:**
     * Durante o depoimento do RECLAMANTE:
       - Apenas o Juiz e o(s) Advogado(s) da(s) Reclamada(s) podem fazer perguntas
       - O Advogado do Reclamante NÃO pode fazer perguntas ao seu próprio cliente
       - O Advogado do Reclamante pode apenas protestar contra perguntas inadequadas
     * Durante o depoimento do PREPOSTO/REPRESENTANTE da Reclamada:
       - Apenas o Juiz e o Advogado do Reclamante podem fazer perguntas
       - O Advogado da Reclamada NÃO pode fazer perguntas ao seu próprio preposto/representante
       - O Advogado da Reclamada pode apenas protestar contra perguntas inadequadas

3. **DEPOIMENTO DAS TESTEMUNHAS:**
   * **CRÍTICO**: Identifique corretamente a ordem das testemunhas conforme a ata:
     - 1ª testemunha do reclamante
     - 2ª testemunha do reclamante
     - 1ª testemunha da reclamada
     - 2ª testemunha da reclamada
   * Ordem obrigatória das perguntas:
     - Primeiro: Juiz
     - Segundo: Advogado da parte que arrolou a testemunha
     - Terceiro: Advogado da parte contrária
   * A testemunha só responde, não faz perguntas

4. **REGRAS GERAIS:**
   * O Juiz pode interromper qualquer depoimento para fazer perguntas ou esclarecer pontos
   * Questões de ordem devem ser identificadas como tal
   * Protestos devem ser claramente marcados

**INSTRUÇÕES ESPECÍFICAS PARA IDENTIFICAÇÃO:**

1. **ANÁLISE DA ATA:**
   * **IGNORE** a primeira folha (folha de rosto) - use apenas as informações após "ATA DE AUDIÊNCIA"
   * Identifique TODOS os presentes na seção "Presente a parte..."
   * Verifique se os depoimentos foram "gravados" ou "dispensados"
   * Identifique TODAS as testemunhas e sua ordem

2. **IDENTIFICAÇÃO NA TRANSCRIÇÃO:**
   * Use os nomes EXATOS da ata quando disponíveis
   * Siga a ordem processual para identificar interlocutores
   * **CRÍTICO**: Não confunda testemunhas com partes
   * **CRÍTICO**: Identifique corretamente quem faz perguntas a quem
   * Use rótulos genéricos apenas quando for impossível identificar

3. **FORMATAÇÃO:**
   * Mantenha timestamps originais se presentes
   * Use o formato: [HH:MM:SS --> HH:MM:SS] INTERLOCUTOR: Texto
   * Não adicione timestamps se não existirem no original
   * Não adicione títulos ou seções extras

4. **QUALIDADE:**
   * Mantenha o texto original inalterado
   * Não corrija erros gramaticais ou de fala
   * Não adicione ou remova conteúdo
   * Preserve hesitações, repetições e características da fala

{labels}

**TRANSCRIÇÃO ORIGINAL PARA PROCESSAR:**
"""
    
    if transcript_text_chunk:
        prompt += f"\n{transcript_text_chunk}"
    
    return prompt

# --- Classe de Sinais (WorkerSignals) ---
class WorkerSignals(QObject):
    message = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

# --- Classe Principal da Janela (TranscriptionWindow) ---
class TranscriptionWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Transcrição Multicanal de Audiências Trabalhistas (4 Canais)")
        self.setMinimumSize(850, 750)
        self.saved_keys = load_api_keys()
        self.worker_signals = WorkerSignals()
        self.worker_signals.message.connect(self.update_message_box)
        self.worker_signals.finished.connect(self.on_transcription_finished)
        self.worker_signals.error.connect(self.on_transcription_error)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setSpacing(10)
        controls_layout.setContentsMargins(0,0,0,0)

        # --- Informação sobre Canais ---
        channel_info_group = QWidget()
        channel_info_layout = QVBoxLayout(channel_info_group)
        channel_info_layout.setContentsMargins(0,0,0,0)
        channel_info_label = QLabel("<b>Este script processa áudios multicanal (4+ canais):</b>")
        channel_mapping_label = QLabel("Canal 1: Juiz | Canal 2: Adv. Reclamante | Canal 3: Adv. Reclamado | Canal 4: Depoente")
        channel_mapping_label.setStyleSheet("color: #666; font-style: italic;")
        channel_note_label = QLabel("Nota: Arquivos com 8 canais (MixPre-6M) são aceitos - apenas os primeiros 4 são processados")
        channel_note_label.setStyleSheet("color: #888; font-size: 11px;")
        channel_info_layout.addWidget(channel_info_label)
        channel_info_layout.addWidget(channel_mapping_label)
        channel_info_layout.addWidget(channel_note_label)
        controls_layout.addWidget(channel_info_group)

        # --- 1. Arquivos de Entrada ---
        file_input_group = QWidget()
        file_input_layout = QVBoxLayout(file_input_group)
        file_input_layout.setContentsMargins(0, 5, 0, 5)
        file_input_label = QLabel("<b>1. Arquivos de Entrada:</b>")
        file_input_layout.addWidget(file_input_label)
        # Arquivo de áudio
        audio_group = QHBoxLayout()
        audio_label = QLabel("Áudio WAV (4+ canais):")
        self.audio_input = QLineEdit()
        self.audio_input.setPlaceholderText("Selecione arquivo WAV multicanal (4+ canais, ex: MixPre-6M com 8 canais)")
        audio_browse_btn = QPushButton("Procurar...")
        audio_browse_btn.setToolTip("Procurar arquivo WAV multicanal (4+ canais)")
        audio_browse_btn.clicked.connect(lambda: self.browse_file_dialog('audio'))
        audio_group.addWidget(audio_label)
        audio_group.addWidget(self.audio_input)
        audio_group.addWidget(audio_browse_btn)
        file_input_layout.addLayout(audio_group)
        # Arquivo da ata
        ata_group = QHBoxLayout()
        ata_label = QLabel("Ata:")
        self.ata_input = QLineEdit()
        self.ata_input.setPlaceholderText("Obrigatório: Selecione o arquivo da ata (.pdf, .txt) para identificar depoentes")
        ata_browse_btn = QPushButton("Procurar...")
        ata_browse_btn.setToolTip("Procurar arquivo da ata em formato PDF ou TXT")
        ata_browse_btn.clicked.connect(lambda: self.browse_file_dialog('ata'))
        ata_group.addWidget(ata_label)
        ata_group.addWidget(self.ata_input)
        ata_group.addWidget(ata_browse_btn)
        file_input_layout.addLayout(ata_group)
        controls_layout.addWidget(file_input_group)

        # --- 2. Serviço de Pós-processamento ---
        service_group = QWidget()
        service_layout = QHBoxLayout(service_group)
        service_layout.setContentsMargins(0,0,0,0)
        service_label = QLabel("<b>2. Serviço de Pós-processamento:</b>")
        self.service_claude = QRadioButton("Claude (3.5 Sonnet)")
        self.service_openai = QRadioButton("OpenAI (GPT-4o)")
        self.service_gemini = QRadioButton("Gemini (2.5 Flash)")
        self.service_claude.setChecked(True) # Padrão
        service_layout.addWidget(service_label)
        service_layout.addWidget(self.service_claude)
        service_layout.addWidget(self.service_openai)
        service_layout.addWidget(self.service_gemini)
        service_layout.addStretch()
        controls_layout.addWidget(service_group)

        # --- 3. Configuração das APIs ---
        keys_group = QWidget()
        keys_layout = QVBoxLayout(keys_group)
        keys_layout.setSpacing(8)
        keys_layout.setContentsMargins(0, 10, 0, 5)
        keys_title = QLabel("<b>3. Configuração das APIs (Chaves/Credenciais):</b>")
        keys_layout.addWidget(keys_title)

        # Assembly AI API Key
        api_assembly_layout = QHBoxLayout()
        api_assembly_label = QLabel("AssemblyAI Key:")
        self.api_key_assembly_input = QLineEdit(self.saved_keys.get('assembly_ai', ''))
        self.api_key_assembly_input.setPlaceholderText("Necessária para Transcrição (pode usar padrão)")
        self.api_key_assembly_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_assembly_layout.addWidget(api_assembly_label)
        api_assembly_layout.addWidget(self.api_key_assembly_input)
        keys_layout.addLayout(api_assembly_layout)

        # Claude API Key
        self.api_claude_container = QWidget()
        api_claude_layout = QHBoxLayout(self.api_claude_container)
        api_claude_layout.setContentsMargins(0, 0, 0, 0)
        api_claude_label = QLabel("Claude Key:")
        self.api_key_claude_input = QLineEdit(self.saved_keys.get('claude', ''))
        self.api_key_claude_input.setPlaceholderText("Necessária para Pós-processamento Claude")
        self.api_key_claude_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_claude_layout.addWidget(api_claude_label)
        api_claude_layout.addWidget(self.api_key_claude_input)
        keys_layout.addWidget(self.api_claude_container)

        # OpenAI API Key
        self.api_openai_container = QWidget()
        api_openai_layout = QHBoxLayout(self.api_openai_container)
        api_openai_layout.setContentsMargins(0, 0, 0, 0)
        api_openai_label = QLabel("OpenAI Key:")
        self.api_key_openai_input = QLineEdit(self.saved_keys.get('openai', ''))
        self.api_key_openai_input.setPlaceholderText("Necessária para Pós-processamento GPT")
        self.api_key_openai_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_openai_layout.addWidget(api_openai_label)
        api_openai_layout.addWidget(self.api_key_openai_input)
        keys_layout.addWidget(self.api_openai_container)

        # Gemini API Key
        self.api_gemini_container = QWidget()
        api_gemini_layout = QHBoxLayout(self.api_gemini_container)
        api_gemini_layout.setContentsMargins(0, 0, 0, 0)
        api_gemini_label = QLabel("Gemini Key:")
        self.api_key_gemini_input = QLineEdit(self.saved_keys.get('gemini', ''))
        self.api_key_gemini_input.setPlaceholderText("Necessária para Pós-processamento Gemini")
        self.api_key_gemini_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_gemini_layout.addWidget(api_gemini_label)
        api_gemini_layout.addWidget(self.api_key_gemini_input)
        keys_layout.addWidget(self.api_gemini_container)

        controls_layout.addWidget(keys_group)

        # --- 4. Botões de Ação ---
        action_group = QWidget()
        action_layout = QHBoxLayout(action_group)
        action_layout.setContentsMargins(0, 10, 0, 0)
        
        self.transcribe_btn = QPushButton("🎙️ Iniciar Transcrição Multicanal")
        self.transcribe_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.transcribe_btn.clicked.connect(self.start_transcription)
        
        self.stop_btn = QPushButton("⏹️ Parar")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_transcription)
        self.stop_btn.setEnabled(False)
        
        action_layout.addWidget(self.transcribe_btn)
        action_layout.addWidget(self.stop_btn)
        action_layout.addStretch()
        
        controls_layout.addWidget(action_group)

        # --- 5. Caixa de Mensagens ---
        messages_group = QWidget()
        messages_layout = QVBoxLayout(messages_group)
        messages_layout.setContentsMargins(0, 10, 0, 0)
        messages_label = QLabel("<b>4. Log de Execução:</b>")
        messages_layout.addWidget(messages_label)
        
        self.message_box = QTextEdit()
        self.message_box.setReadOnly(True)
        self.message_box.setMaximumHeight(200)
        self.message_box.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
        """)
        messages_layout.addWidget(self.message_box)
        
        controls_layout.addWidget(messages_group)

        main_layout.addWidget(controls_widget)
        main_layout.addStretch()

        # --- Configuração de Visibilidade ---
        self.update_ui_visibility()

        # --- Timer para atualização de status ---
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.running = False

    def update_ui_visibility(self):
        """Atualiza a visibilidade dos campos de API baseado no serviço selecionado."""
        # Sempre mostrar AssemblyAI (obrigatório)
        # Mostrar/ocultar outros baseado na seleção
        self.api_claude_container.setVisible(self.service_claude.isChecked())
        self.api_openai_container.setVisible(self.service_openai.isChecked())
        self.api_gemini_container.setVisible(self.service_gemini.isChecked())

    def browse_file_dialog(self, file_type):
        """Abre diálogo para seleção de arquivo."""
        if file_type == 'audio':
            file_path, _ = QFileDialog.getOpenFileName(
                self, 
                "Selecionar Arquivo de Áudio WAV (4 canais)", 
                get_download_dir(),
                "Arquivos WAV (*.wav);;Todos os arquivos (*.*)"
            )
            if file_path:
                self.audio_input.setText(file_path)
        elif file_type == 'ata':
            file_path, _ = QFileDialog.getOpenFileName(
                self, 
                "Selecionar Arquivo da Ata", 
                get_download_dir(),
                "Arquivos PDF (*.pdf);;Arquivos de Texto (*.txt);;Todos os arquivos (*.*)"
            )
            if file_path:
                self.ata_input.setText(file_path)

    def update_message_box(self, message):
        """Atualiza a caixa de mensagens."""
        self.message_box.append(message)
        # Auto-scroll para o final
        cursor = self.message_box.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.message_box.setTextCursor(cursor)

    def update_status(self):
        """Atualiza o status da aplicação."""
        if not self.running:
            self.status_timer.stop()

    def start_transcription(self):
        """Inicia o processo de transcrição."""
        # Validações básicas
        audio_path = self.audio_input.text().strip()
        ata_path = self.ata_input.text().strip()
        
        if not audio_path:
            QMessageBox.warning(self, "Erro", "Por favor, selecione um arquivo de áudio WAV.")
            return
        
        if not ata_path:
            QMessageBox.warning(self, "Erro", "Por favor, selecione o arquivo da ata.")
            return
        
        if not os.path.exists(audio_path):
            QMessageBox.warning(self, "Erro", "Arquivo de áudio não encontrado.")
            return
        
        if not os.path.exists(ata_path):
            QMessageBox.warning(self, "Erro", "Arquivo da ata não encontrado.")
            return

        # Verificar se é arquivo WAV
        if not audio_path.lower().endswith('.wav'):
            QMessageBox.warning(self, "Erro", "Este script requer arquivo WAV multicanal.")
            return

        # Verificar número de canais
        num_channels = get_audio_channels(audio_path)
        if num_channels < 4:
            QMessageBox.warning(self, "Erro", f"Este script requer arquivo WAV com pelo menos 4 canais. Arquivo selecionado tem {num_channels} canal(is).")
            return
        elif num_channels > 4:
            self.worker_signals.message.emit(f"ℹ️ Arquivo com {num_channels} canais detectado. Usando apenas os primeiros 4 canais.")

        # Obter API keys
        api_key_assembly = self.api_key_assembly_input.text().strip()
        api_key_claude = self.api_key_claude_input.text().strip()
        api_key_openai = self.api_key_openai_input.text().strip()
        api_key_gemini = self.api_key_gemini_input.text().strip()

        # Salvar chaves
        save_api_keys(api_key_assembly, api_key_claude, api_key_openai, api_key_gemini)

        # Configurar interface
        self.running = True
        self.transcribe_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.message_box.clear()

        # Iniciar thread de transcrição
        self.transcription_thread = threading.Thread(
            target=self.perform_transcription_workflow,
            args=(audio_path, ata_path, api_key_assembly, api_key_openai, api_key_claude, api_key_gemini)
        )
        self.transcription_thread.daemon = True
        self.transcription_thread.start()

    def stop_transcription(self):
        """Para o processo de transcrição."""
        self.running = False
        self.transcribe_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.worker_signals.message.emit("⏹️ Processo interrompido pelo usuário.")

    def on_transcription_finished(self):
        """Chamado quando a transcrição é concluída."""
        self.running = False
        self.transcribe_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def on_transcription_error(self, error_message):
        """Chamado quando ocorre um erro na transcrição."""
        self.running = False
        self.transcribe_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        QMessageBox.critical(self, "Erro", f"Erro durante a transcrição:\n{error_message}")

    def perform_transcription_workflow(self, file_path_or_url, ata_path, api_key_assembly, api_key_openai, api_key_claude, api_key_gemini):
        """Executa o workflow completo de transcrição e pós-processamento."""
        try:
            # Verificar se deve continuar
            if not self.running:
                return

            # Determinar destino do arquivo
            base_name = os.path.splitext(os.path.basename(file_path_or_url))[0]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            destination_filename = f"{base_name}_transcricao_multicanal_{timestamp}.txt"
            full_destination_path = os.path.join(get_download_dir(), destination_filename)

            self.worker_signals.message.emit(f"📁 Arquivo de destino: {destination_filename}")
            self.worker_signals.message.emit(f"📂 Pasta de destino: {get_download_dir()}")

            # Verificar duração do áudio
            if not (file_path_or_url.startswith('http://') or file_path_or_url.startswith('https://')):
                audio_duration_ms = get_audio_duration_from_path(file_path_or_url)
                audio_duration_minutes = audio_duration_ms / 60000
                self.worker_signals.message.emit(f"📊 Duração do áudio: {ms_to_formatted_time(audio_duration_ms)} ({audio_duration_minutes:.1f} minutos)")
                estimated_completion = get_estimated_transcription_time(audio_duration_ms)
                self.worker_signals.message.emit(f"⏰ Previsão de conclusão: {estimated_completion}")

            # Verificar se deve continuar
            if not self.running:
                return

            # Extrair informações da ata
            self.worker_signals.message.emit("📄 Extraindo informações da ata...")
            ata_info = format_ata_info(ata_path)
            depoentes = parse_depoentes_from_ata(extract_info_from_ata(ata_path))
            
            if depoentes:
                self.worker_signals.message.emit(f"👥 Depoentes identificados: {len(depoentes)}")
                for i, (tipo, nome) in enumerate(depoentes, 1):
                    self.worker_signals.message.emit(f"   {i}. {tipo}: {nome}")
            else:
                self.worker_signals.message.emit("⚠️ Aviso: Nenhum depoente identificado na ata")

            # Verificar se deve continuar
            if not self.running:
                return

            # Configurar AssemblyAI
            effective_assembly_key = api_key_assembly if api_key_assembly else self.saved_keys.get('assembly_ai')
            if not effective_assembly_key:
                effective_assembly_key = "3df027b3d3f0494287f65e04610d0a47"
                self.worker_signals.message.emit("ℹ️ Usando API Key padrão da AssemblyAI.")
            
            aai.settings.api_key = effective_assembly_key

            self.worker_signals.message.emit("🗣️ Configurando AssemblyAI para transcrição multicanal (4 canais)...")
            config_params = {
                "language_code": "pt",
                "multichannel": True,  # Sempre True para 4 canais
                "speaker_labels": False,  # Incompatível com multichannel
                "word_boost": ["juiz", "juíza", "excelência", "reclamante", "reclamada", "preposto", "preposta", "advogado", "advogada", "testemunha", "depoimento", "contradita", "indeferido", "deferido", "pela ordem", "questão de ordem", "autos", "sentença", "acórdão", "liminar", "tutela", "mérito", "ônus da prova", "cartão de ponto", "horas extras", "intervalo", "verbas rescisórias"],
                "boost_param": "high"
            }

            config = aai.TranscriptionConfig(**config_params)
            transcriber = aai.Transcriber()
            
            self.worker_signals.message.emit("🎙️ Iniciando transcrição com AssemblyAI...")
            start_transcription_time = time.time()
            
            transcript = transcriber.transcribe(file_path_or_url, config=config)

            if transcript.status == aai.TranscriptStatus.error:
                raise RuntimeError(f"Erro AssemblyAI: {transcript.error}")
            if transcript.status != aai.TranscriptStatus.completed:
                raise RuntimeError(f"Transcrição AssemblyAI não completou (Status: {transcript.status}).")

            transcription_time = time.time() - start_transcription_time
            self.worker_signals.message.emit(f"⏱️ Tempo de transcrição: {transcription_time:.1f} segundos")

            # Verificar se deve continuar
            if not self.running:
                return

            # Processar transcrição
            if transcript.utterances:
                utterance_count = 0
                current_depoente_index = 0
                last_depoente_time = 0
                
                with open(full_destination_path, 'w', encoding='utf-8') as file:
                    for utterance in transcript.utterances:
                        # Mapear canal para papel
                        try:
                            channel = int(utterance.channel) if utterance.channel is not None else -1
                        except (ValueError, TypeError):
                            channel = -1
                        
                        if channel == 0:
                            speaker = "Juiz"
                        elif channel == 1:
                            speaker = "Advogado do Reclamante"
                        elif channel == 2:
                            speaker = "Advogado do Reclamado"
                        elif channel == 3:
                            # Lógica para identificar depoente atual
                            if depoentes and current_depoente_index < len(depoentes):
                                # Detectar mudança de depoente (pausa > 30 segundos)
                                if utterance.start - last_depoente_time > 30000 and last_depoente_time > 0:
                                    current_depoente_index += 1
                                    if current_depoente_index < len(depoentes):
                                        self.worker_signals.message.emit(f"🔄 Mudança de depoente: {depoentes[current_depoente_index][0]}")
                                
                                if current_depoente_index < len(depoentes):
                                    speaker = depoentes[current_depoente_index][0]
                                else:
                                    speaker = "Depoente Desconhecido"
                                last_depoente_time = utterance.end
                            else:
                                speaker = "Depoente"
                        else:
                            speaker = f"Canal {channel + 1}" if channel >= 0 else "Canal Desconhecido"

                        start_time_f = ms_to_formatted_time(utterance.start)
                        end_time_f = ms_to_formatted_time(utterance.end)
                        line = f"[{start_time_f} --> {end_time_f}] {speaker}: {utterance.text}\n"
                        file.write(line)
                        utterance_count += 1

                if utterance_count > 0:
                    self.worker_signals.message.emit(f"✅ Transcrição multicanal concluída ({utterance_count} falas).")
                    transcript_success = True
                else:
                    self.worker_signals.message.emit("⚠️ Aviso: AssemblyAI concluiu, mas não retornou falas.")
                    transcript_success = False
            else:
                self.worker_signals.message.emit("⚠️ Aviso: AssemblyAI completou sem erros, mas sem 'utterances'.")
                transcript_success = False

            # Verificar se deve continuar
            if not self.running:
                return

            # Pós-processamento se solicitado
            if transcript_success:
                selected_service = ""
                if self.service_claude.isChecked():
                    selected_service = "Claude"
                elif self.service_openai.isChecked():
                    selected_service = "GPT-4o"
                elif self.service_gemini.isChecked():
                    selected_service = "Gemini"

                if selected_service:
                    self.worker_signals.message.emit(f"🔄 Iniciando pós-processamento com {selected_service}...")
                    
                    # Ler transcrição
                    with open(full_destination_path, 'r', encoding='utf-8') as file:
                        transcript_text = file.read()

                    # Criar prompt
                    prompt = create_post_processing_prompt(ata_info, transcript_text)

                    # Executar pós-processamento
                    if selected_service == "Claude" and api_key_claude:
                        # Implementar pós-processamento Claude
                        self.worker_signals.message.emit("🤖 Pós-processamento com Claude em desenvolvimento...")
                    elif selected_service == "GPT-4o" and api_key_openai:
                        # Implementar pós-processamento OpenAI
                        self.worker_signals.message.emit("🤖 Pós-processamento com GPT-4o em desenvolvimento...")
                    elif selected_service == "Gemini" and api_key_gemini:
                        # Implementar pós-processamento Gemini
                        self.worker_signals.message.emit("🤖 Pós-processamento com Gemini em desenvolvimento...")
                    else:
                        self.worker_signals.message.emit("⚠️ Aviso: API Key não fornecida para pós-processamento.")

            # Finalizar
            if transcript_success:
                self.worker_signals.message.emit(f"🎉 Processo concluído com sucesso!")
                self.worker_signals.message.emit(f"📄 Arquivo salvo: {full_destination_path}")
            else:
                self.worker_signals.message.emit("❌ Processo concluído com erros.")

        except Exception as e:
            import traceback
            error_msg = f"Erro durante o processo: {str(e)}"
            self.worker_signals.message.emit(f"❌ {error_msg}")
            print(f"Traceback Error:\n{traceback.format_exc()}")
            self.worker_signals.error.emit(error_msg)
        finally:
            self.worker_signals.finished.emit()

    def closeEvent(self, event):
        """Manipula o evento de fechamento da janela."""
        if self.running:
            reply = QMessageBox.question(self, 'Confirmar Saída', 
                                       'O processo de transcrição está em andamento. Deseja realmente sair?',
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                       QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.running = False
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def main():
    """Função principal da aplicação."""
    app = QApplication(sys.argv)
    app.setApplicationName("KiwiscribeMulti")
    app.setApplicationVersion("1.0")
    
    window = TranscriptionWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
