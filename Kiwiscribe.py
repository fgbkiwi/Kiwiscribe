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
                             QMessageBox, QComboBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QBrush, QColor, QPixmap, QIcon
import openai
from openai import OpenAI
import google.genai as genai # Import simplificado para Gemini

try:
    from KiwiscribeWord import generate_word_document
    DOCX_GENERATOR_AVAILABLE = True
except Exception:
    generate_word_document = None
    DOCX_GENERATOR_AVAILABLE = False

APP_VERSION = "1.0.1"

TRANSCRIPTION_MODELS = {
    "AssemblyAI": [("Universal-3 Pro", "universal-3-pro"), ("Universal-2", "universal-2")],
    "gpt-4o-transcribe": [("gpt-4o-transcribe", "gpt-4o-transcribe"), ("gpt-4o-mini-transcribe", "gpt-4o-mini-transcribe"), ("whisper-1", "whisper-1")],
    "Gemini": [("gemini-2.5-flash", "gemini-2.5-flash"), ("gemini-2.5-pro", "gemini-2.5-pro")],
    "OpenRouter": [("Gemini 2.5 Flash", "google/gemini-2.5-flash"), ("Gemini 2.5 Pro", "google/gemini-2.5-pro"), ("GPT-4o Audio", "openai/gpt-4o-audio-preview")],
    "Soniox": [("soniox/stt-async", "soniox_async")],
    "JustPostProcess": [("Arquivo TXT local", "local_txt")],
    "JustGenerateDocx": [("Arquivo TXT local", "local_txt")],
}

POST_PROCESSING_MODELS = {
    "Claude": [("claude-3-7-sonnet-latest", "claude-3-7-sonnet-latest"), ("claude-sonnet-4-5", "claude-sonnet-4-5")],
    "OpenAI": [("gpt-4o-mini", "gpt-4o-mini"), ("gpt-4o", "gpt-4o"), ("gpt-5-mini", "gpt-5-mini"), ("gpt-5", "gpt-5")],
    "Gemini": [("gemini-2.5-flash", "gemini-2.5-flash"), ("gemini-2.5-pro", "gemini-2.5-pro")],
    "OpenRouter": [("OpenAI GPT-4o mini", "openai/gpt-4o-mini"), ("Claude Sonnet Latest", "~anthropic/claude-sonnet-latest"), ("Gemini Flash Latest", "~google/gemini-flash-latest")],
    "None": [("Nenhum", "none")],
}

# --- Configuração Inicial Gemini ---
# Configuração para google-genai - usa apenas a chave API fornecida pelo usuário na interface
# (Removido o aviso sobre credenciais do ambiente - aceita apenas chave fornecida pelo usuário)

# --- Funções Auxiliares (get_download_dir, load/save_api_keys, ms_to_formatted_time, etc.) ---
# (Mantidas como na versão anterior, sem alterações significativas aqui)
# ... (O código das funções auxiliares permanece o mesmo) ...
# Verifica qual é a localização (default) da pasta de downloads do usuário
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
    keys = {
        'assembly_ai': '',
        'claude': '',
        'openai': '',
        'openai_transcription': '',
        'openai_post': '',
        'gemini': '',
        'gemini_transcription': '',
        'gemini_post': '',
        'soniox': '',
        'openrouter': ''
    } # Padrão
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded_keys = json.load(f)
                # Atualiza o dicionário padrão apenas com as chaves encontradas no arquivo
                keys.update(loaded_keys)
                if not keys.get('openai_transcription') and keys.get('openai'):
                    keys['openai_transcription'] = keys.get('openai', '')
                if not keys.get('openai_post') and keys.get('openai'):
                    keys['openai_post'] = keys.get('openai', '')
                if not keys.get('gemini_transcription') and keys.get('gemini'):
                    keys['gemini_transcription'] = keys.get('gemini', '')
                if not keys.get('gemini_post') and keys.get('gemini'):
                    keys['gemini_post'] = keys.get('gemini', '')
        except (json.JSONDecodeError, IOError) as e:
             print(f"Erro ao carregar arquivo de configuração ({CONFIG_FILE}): {e}. Usando valores padrão.")
    return keys

def save_api_keys(assembly_key, claude_key, openai_key, gemini_key, soniox_key, openai_transcription_key=None, openai_post_key=None, gemini_transcription_key=None, gemini_post_key=None, openrouter_key=None):
    """Salva as chaves de API no arquivo de configuração JSON."""
    config = {
        'assembly_ai': assembly_key,
        'claude': claude_key,
        'openai': openai_key,
        'openai_transcription': openai_transcription_key if openai_transcription_key is not None else openai_key,
        'openai_post': openai_post_key if openai_post_key is not None else openai_key,
        'gemini': gemini_key,
        'gemini_transcription': gemini_transcription_key if gemini_transcription_key is not None else gemini_key,
        'gemini_post': gemini_post_key if gemini_post_key is not None else gemini_key,
        'soniox': soniox_key,
        'openrouter': openrouter_key if openrouter_key is not None else ''
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
    # Estimativa: AssemblyAI leva ~1/4 do tempo do áudio. OpenAI GPT/Gemini podem variar.
    # Usa um fator conservador (ex: 0.6) para abranger todos e adiciona margem.
    factor = 0.6
    estimated_processing_duration = timedelta(milliseconds=recording_duration_ms * factor)
    # Adiciona um tempo base fixo para inicialização, upload, etc. (ex: 2 minutos)
    base_time = timedelta(minutes=2)
    completion_time = datetime.now() + estimated_processing_duration + base_time
    return completion_time.strftime("%Hh%M")

def extract_info_from_ata(ata_path):
    """Extrai informações relevantes (Juiz, partes, advogados, testemunhas) de um arquivo de ata (.txt ou .pdf)."""
    # (Código da função mantido como na versão anterior)
    try:
        text = ""
        if not os.path.exists(ata_path):
            return "Erro: Arquivo da ata não encontrado."
        if not ata_path.lower().endswith(('.pdf', '.txt')):
             return "Erro: Formato de arquivo da ata não suportado (use .pdf ou .txt)."

        print(f"Lendo arquivo da ata: {ata_path}")
        if ata_path.lower().endswith('.pdf'):
            try:
                with open(ata_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    if reader.is_encrypted:
                         try:
                            decrypt_result = reader.decrypt('')
                            if decrypt_result == 0:
                                print("Aviso: PDF criptografado, tentando descriptografar sem senha.")
                                # Se falhar, a extração abaixo provavelmente retornará vazio ou erro
                         except Exception as decrypt_error:
                              print(f"Erro ao tentar descriptografar PDF: {decrypt_error}")
                              # Pode ser necessário senha, retorna erro claro
                              return "Erro: O arquivo PDF está criptografado e requer senha."

                    num_pages = len(reader.pages)
                    print(f"Extraindo texto de {num_pages} páginas do PDF...")
                    for i, page in enumerate(reader.pages):
                         try:
                              page_text = page.extract_text()
                              if page_text:
                                   text += page_text + "\n"
                         except Exception as page_error:
                              print(f"Aviso: Erro ao extrair texto da página {i+1} do PDF: {page_error}")
                              continue
            except Exception as pdf_error:
                 return f"Erro crítico ao ler o arquivo PDF: {str(pdf_error)}"

        elif ata_path.lower().endswith('.txt'):
             try:
                  # Tenta detectar a codificação (utf-8 é comum, mas pode variar)
                  encodings_to_try = ['utf-8', 'latin-1', 'cp1252']
                  detected_encoding = None
                  for enc in encodings_to_try:
                       try:
                            with open(ata_path, 'r', encoding=enc) as file:
                                 text = file.read()
                            detected_encoding = enc
                            print(f"Arquivo de texto lido com encoding: {enc}")
                            break # Sai do loop se a leitura for bem-sucedida
                       except UnicodeDecodeError:
                            continue # Tenta próximo encoding
                  if not detected_encoding:
                       return f"Erro: Não foi possível decodificar o arquivo de texto {os.path.basename(ata_path)} com os encodings testados (UTF-8, Latin-1, CP1252)."
             except Exception as txt_error:
                  return f"Erro ao ler o arquivo de texto: {str(txt_error)}"

        if not text or not text.strip():
             return "Erro: O arquivo da ata parece estar vazio ou o texto não pôde ser extraído."

        # Normaliza espaços e quebras de linha para facilitar Regex
        text = re.sub(r'\s+', ' ', text).strip()
        full_text = text
        
        # CRÍTICO: Extrai texto apenas a partir de "ATA DE AUDIÊNCIA"
        ata_start = re.search(r'ATA DE AUDIÊNCIA', text, re.IGNORECASE)
        if ata_start:
            text = text[ata_start.start():]
            print(f"Texto extraído a partir de 'ATA DE AUDIÊNCIA' (primeiros 500 chars): {text[:500]}...")
        else:
            print("AVISO: Não foi encontrado 'ATA DE AUDIÊNCIA' no texto. Usando texto completo.")
            print(f"Texto extraído da ata (primeiros 500 chars): {text[:500]}...")

        info = {
            'juiz': None,
            'reclamante': None,
            'advogado_reclamante': None,
            'advogado_reclamante_oab': None,
            'reclamadas': [],
            'advogados_reclamadas': [],
            'advogados_reclamadas_oab': [],
            'prepostos': [],
            'testemunhas_reclamante': [],
            'testemunhas_reclamante_numeros': [],
            'testemunhas_reclamante_status': [],
            'testemunhas_reclamada': [],
            'testemunhas_reclamada_numeros': [],
            'testemunhas_reclamada_status': [],
            'depoimento_reclamante': 'não mencionado',
            'depoimento_reclamado': 'não mencionado'
        }

        # Regex aprimorados e mais flexíveis (case-insensitive)
        # Juiz: Procura por "Juiz(a) do Trabalho", "Juiz(a) Federal do Trabalho", etc., seguido por um nome
        juiz_pattern = r'Juiz\(?a?\)?(?: Federal)? do Trabalho\s*(?:Substituto\(?a?\)?\s*)?:?\s+([A-ZÀ-Úa-zà-ú\s\'\.-]+?)(?:,|\s(?:CPF|PRESIDENTE)|\s*$)';
        juiz_match = re.search(juiz_pattern, text, re.IGNORECASE)
        if juiz_match:
            info['juiz'] = ' '.join(juiz_match.group(1).strip().split()).title() # Limpa espaços extras e capitaliza
            print(f"Juiz encontrado: {info['juiz']}")
        else:
            print("Juiz não encontrado com o padrão principal.")
             # Tentar um padrão alternativo mais simples? Ex: PRESIDENTE E JUIZ DO TRABALHO: NOME
            juiz_alt_match = re.search(r'(?:PRESIDENTE E )?JUIZ DO TRABALHO\s*:\s*([A-ZÀ-Ú\s]+)', text, re.IGNORECASE)
            if juiz_alt_match:
                 info['juiz'] = juiz_alt_match.group(1).strip().title()
                 print(f"Juiz encontrado (padrão alternativo): {info['juiz']}")


        # Reclamante e Advogado(a): PADRÕES SIMPLIFICADOS E EFICIENTES
        reclamante_encontrado = False

        def _limpar_oab(valor):
            return ' '.join(valor.strip().split()).upper().rstrip('.,;')

        def _limpar_nome(valor):
            return ' '.join(valor.strip().split()).strip(' -')
        
        # Padrão 1: "Presente a parte reclamante NOME, pessoalmente, acompanhado(a) de seu(a) advogado(a), Dr(a). NOME, OAB"
        recl_pattern1 = (
            r'Presente a parte reclamante ([^,]+), pessoalmente, acompanhado\(?a?\)? de seu(?:\s*\(?a?\)?)?\s*advogado\(?a?\), '
            r'Dr\(?a?\)\. ([^,]+),\s*(OAB(?:/[A-Z]{2})?\s*[\d\.\-/A-Z]+)'
        )
        reclamante_match = re.search(recl_pattern1, text, re.IGNORECASE)
        if reclamante_match:
            info['reclamante'] = ' '.join(reclamante_match.group(1).strip().split()).title()
            info['advogado_reclamante'] = ' '.join(reclamante_match.group(2).strip().split()).title()
            info['advogado_reclamante_oab'] = _limpar_oab(reclamante_match.group(3))
            print(f"Reclamante encontrado (padrão 1): {info['reclamante']}, Adv: {info['advogado_reclamante']}")
            reclamante_encontrado = True
        
        # Padrão 2: "Presente a parte reclamante NOME, ... Dr(a). NOME, OAB" (mais flexível)
        if not reclamante_encontrado:
            recl_pattern2 = r'Presente a parte reclamante ([^,]+),.*?Dr\(?a?\)\. ([^,]+),\s*(OAB(?:/[A-Z]{2})?\s*[\d\.\-/A-Z]+)'
            reclamante_match = re.search(recl_pattern2, text, re.IGNORECASE | re.DOTALL)
            if reclamante_match:
                info['reclamante'] = ' '.join(reclamante_match.group(1).strip().split()).title()
                info['advogado_reclamante'] = ' '.join(reclamante_match.group(2).strip().split()).title()
                info['advogado_reclamante_oab'] = _limpar_oab(reclamante_match.group(3))
                print(f"Reclamante encontrado (padrão 2): {info['reclamante']}, Adv: {info['advogado_reclamante']}")
                reclamante_encontrado = True
        
        # Padrão 3: "RECLAMANTE: NOME ADVOGADO: NOME" (folha de rosto)
        if not reclamante_encontrado:
            recl_pattern3 = (
                r'RECLAMANTE\s*:\s*(.+?)\s+ADVOGADO\s*:\s*(.+?)'
                r'(?:\s+(OAB(?:/[A-Z]{2})?\s*[\d\.\-/A-Z]+))?'
                r'(?=\s+(?:RECLAMAD[OA]|ATA DE AUDIÊNCIA)|$)'
            )
            reclamante_match = re.search(recl_pattern3, full_text, re.IGNORECASE | re.DOTALL)
            if reclamante_match:
                info['reclamante'] = reclamante_match.group(1).strip().title()
                info['advogado_reclamante'] = reclamante_match.group(2).strip().title()
                if reclamante_match.group(3):
                    info['advogado_reclamante_oab'] = _limpar_oab(reclamante_match.group(3))
                print(f"Reclamante encontrado (padrão 3 - folha de rosto): {info['reclamante']}, Adv: {info['advogado_reclamante']}")
                reclamante_encontrado = True
        
        if not reclamante_encontrado:
            print("AVISO: Nome do Reclamante ou seu Advogado não encontrado na ata.")


        def _extrair_advogados_do_bloco(bloco):
            advogados = []
            oabs = []
            for adv_match in re.finditer(
                r'(?:Dr\(?a?\)\.|Dra\.)\s*([^,]+),\s*(OAB(?:/[A-Z]{2})?\s*[\d\.\-/A-Z]+)',
                bloco,
                re.IGNORECASE,
            ):
                nome_adv = ' '.join(adv_match.group(1).strip().split()).title()
                oab_adv = _limpar_oab(adv_match.group(2))
                if nome_adv and nome_adv not in advogados:
                    advogados.append(nome_adv)
                    oabs.append(oab_adv)
            return advogados, oabs

        # Reclamada(s), representante (preposto ou proprietário) e advogado(s)
        reclamada_encontrada = False

        # Padrão 1: preposto(a) ou proprietário(a) Sr.(a) NOME; um ou mais Dr(a)./Dra. com OAB no bloco
        reclamada_block_pattern = (
            r'Presente a parte reclamada (.+?), representado\(?a?\)? pel[oa]\(?a?\)?\s+'
            r'(?:preposto\(?a?\)|propriet[aá]rio\(?a?\))\s+Sr\(?\.?\)?\(?a?\)?\s+([^,]+),'
        )
        matches_reclamada_blocks = list(re.finditer(reclamada_block_pattern, text, re.IGNORECASE))
        if matches_reclamada_blocks:
            print(f"Encontradas {len(matches_reclamada_blocks)} reclamada(s) (preposto/proprietário).")
            reclamada_encontrada = True
            for i, match_reclamada in enumerate(matches_reclamada_blocks, 1):
                nome_reclamada = ' '.join(match_reclamada.group(1).strip().split()).title()
                nome_representante = ' '.join(match_reclamada.group(2).strip().split()).title()
                fim_bloco = match_reclamada.end()
                prox_presente = text.find('Presente a parte', fim_bloco)
                prox_conciliacao = text.find('CONCILIAÇÃO', fim_bloco)
                candidatos_fim = [p for p in (prox_presente, prox_conciliacao) if p >= 0]
                fim = min(candidatos_fim) if candidatos_fim else len(text)
                bloco = text[match_reclamada.start():fim]
                advogados, oabs = _extrair_advogados_do_bloco(bloco)
                info['reclamadas'].append(nome_reclamada)
                info['prepostos'].append(nome_representante)
                info['advogados_reclamadas'].append(advogados if advogados else [])
                info['advogados_reclamadas_oab'].append(oabs if oabs else [])
                adv_resumo = ', '.join(advogados) if advogados else 'N/I'
                print(f"{i}ª Reclamada: {nome_reclamada}, Representante: {nome_representante}, Adv(s): {adv_resumo}")

        # Padrão 2: fallback sem identificação de representante
        if not reclamada_encontrada:
            reclamada_pattern2 = r'Presente a parte reclamada ([^,]+),.*?Dr\(?a?\)\. ([^,]+),\s*(OAB(?:/[A-Z]{2})?\s*[\d\.\-/A-Z]+)'
            matches_reclamada2 = list(re.finditer(reclamada_pattern2, text, re.IGNORECASE))
            if matches_reclamada2:
                print(f"Encontradas {len(matches_reclamada2)} reclamada(s) (padrão 2).")
                reclamada_encontrada = True
                for i, match_reclamada in enumerate(matches_reclamada2, 1):
                    nome_reclamada = ' '.join(match_reclamada.group(1).strip().split()).title()
                    nome_advogado = ' '.join(match_reclamada.group(2).strip().split()).title()
                    oab_advogado = _limpar_oab(match_reclamada.group(3))
                    info['reclamadas'].append(nome_reclamada)
                    info['prepostos'].append("N/I")
                    info['advogados_reclamadas'].append([nome_advogado] if nome_advogado else [])
                    info['advogados_reclamadas_oab'].append([oab_advogado] if oab_advogado else [])
                    print(f"{i}ª Reclamada: {nome_reclamada}, Preposto: N/I, Adv: {nome_advogado}")
        
        # Padrão 3: "RECLAMADO: NOME ADVOGADO: NOME" (folha de rosto)
        if not reclamada_encontrada:
            reclamada_pattern3 = (
                r'RECLAMAD[OA]\s*:\s*(.+?)\s+ADVOGADO\s*:\s*(.+?)'
                r'(?:\s+(OAB(?:/[A-Z]{2})?\s*[\d\.\-/A-Z]+))?'
                r'(?=\s+(?:RECLAMAD[OA]|ATA DE AUDIÊNCIA|TERCEIRO|PERITO)|$)'
            )
            matches = list(re.finditer(reclamada_pattern3, full_text, re.IGNORECASE | re.DOTALL))
            if matches:
                print(f"Encontradas {len(matches)} ocorrências para Reclamada(s) com padrão 3 (folha de rosto).")
                reclamada_encontrada = True
                # Para folha de rosto, não temos preposto, então usamos "N/I"
                for i, match in enumerate(matches):
                    nome_reclamada = ' '.join(match.group(1).strip().split()).title()
                    nome_advogado = ' '.join(match.group(2).strip().split()).title()
                    oab_advogado = _limpar_oab(match.group(3)) if match.group(3) else None
                    info['reclamadas'].append(nome_reclamada)
                    info['prepostos'].append("N/I")
                    info['advogados_reclamadas'].append([nome_advogado] if nome_advogado else [])
                    info['advogados_reclamadas_oab'].append([oab_advogado] if oab_advogado else [])
                    print(f"{i+1}ª Reclamada (folha de rosto): {nome_reclamada}, Preposto: N/I, Adv: {nome_advogado}")
        
        if not reclamada_encontrada:
            print("AVISO: Nenhuma Reclamada encontrada na ata.")

        # Testemunhas: padrões para reclamante, reclamada e "primeira reclamada" (com/sem dois pontos)
        testemunha_encontrada = False
        _nome_testemunha_re = r'([A-ZÀ-Úa-zà-ú][A-ZÀ-Úa-zà-ú\s\'\.-]+?)(?:,\s*CPF|\s+CPF|$)'

        def _status_depoimento_testemunha(pos_inicio):
            prox = re.search(r'\d+ª\s+testemunha|As partes não têm outras provas|Fica encerrada', text[pos_inicio:], re.IGNORECASE)
            fim = pos_inicio + prox.start() if prox else len(text)
            bloco = text[pos_inicio:fim]
            if re.search(r'Depoimento\s+gravado', bloco, re.IGNORECASE):
                return 'gravado'
            if re.search(r'Depoimento\s+dispensado', bloco, re.IGNORECASE):
                return 'dispensado'
            return 'não mencionado'

        def _coletar_testemunhas(patterns, lista_destino, lista_numeros, lista_status, rotulo):
            nonlocal testemunha_encontrada
            por_numero = {}
            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    num_test = int(match.group(1))
                    nome_testemunha = _limpar_nome(match.group(2)).title()
                    if nome_testemunha and num_test not in por_numero:
                        por_numero[num_test] = (nome_testemunha, _status_depoimento_testemunha(match.end()))
            if not por_numero:
                return
            testemunha_encontrada = True
            for num in sorted(por_numero.keys()):
                nome_testemunha, status = por_numero[num]
                lista_destino.append(nome_testemunha)
                lista_numeros.append(num)
                lista_status.append(status)
                print(f"{num}ª Testemunha ({rotulo}): {nome_testemunha} ({status})")
            print(f"Total: {len(por_numero)} testemunha(s) ({rotulo}).")

        _parte_reclamada = r'reclamad[ao](?:\(a\))?'
        test_patterns_reclamante = [
            rf'(\d+)ª\s+testemunha\s+do\(?a?\)?\s+reclamante\s*:\s*{_nome_testemunha_re}',
            rf'(\d+)ª\s+testemunha\s+do\(?a?\)?\s+reclamante\s+{_nome_testemunha_re}',
            rf'(\d+)ª\s+testemunha\s+do\s+reclamante\s*:\s*{_nome_testemunha_re}',
            rf'(\d+)ª\s+testemunha\s+do\s+reclamante\s+{_nome_testemunha_re}',
        ]
        _coletar_testemunhas(
            test_patterns_reclamante,
            info['testemunhas_reclamante'],
            info['testemunhas_reclamante_numeros'],
            info['testemunhas_reclamante_status'],
            'Reclamante',
        )

        test_patterns_reclamada = [
            rf'(\d+)ª\s+testemunha\s+da\s+(?:primeira\s+|1ª\s+)?{_parte_reclamada}\s*:\s*{_nome_testemunha_re}',
            rf'(\d+)ª\s+testemunha\s+da\s+(?:primeira\s+|1ª\s+)?{_parte_reclamada}\s+{_nome_testemunha_re}',
            rf'(\d+)ª\s+testemunha\s+do\(?a?\)?\s+{_parte_reclamada}\s*:\s*{_nome_testemunha_re}',
            rf'(\d+)ª\s+testemunha\s+do\(?a?\)?\s+{_parte_reclamada}\s+{_nome_testemunha_re}',
            rf'(\d+)ª\s+testemunha\s+da\s+reclamad[ao]\s*:\s*{_nome_testemunha_re}',
            rf'(\d+)ª\s+testemunha\s+da\s+reclamad[ao]\s+{_nome_testemunha_re}',
        ]
        _coletar_testemunhas(
            test_patterns_reclamada,
            info['testemunhas_reclamada'],
            info['testemunhas_reclamada_numeros'],
            info['testemunhas_reclamada_status'],
            'Reclamada',
        )

        if not testemunha_encontrada:
            print("AVISO: Nenhuma testemunha encontrada na ata.")

        # Detecta informações sobre depoimentos (gravados ou dispensados) - MELHORADO
        # Padrão 1: "Depoimento pessoal do(a) autor(a) gravado/dispensado"
        depoimento_reclamante_pattern1 = r'Depoimento\s+pessoal\s+d[oa](?:\(a\))?\s+(?:autor|reclamante|parte\s+reclamante)(?:\(a\))?\s+(gravado|dispensado)'
        reclamante_match = re.search(depoimento_reclamante_pattern1, text, re.IGNORECASE)
        if reclamante_match:
            info['depoimento_reclamante'] = reclamante_match.group(1).lower()
            print(f"Depoimento do reclamante: {info['depoimento_reclamante']}")
        
        # Padrão 2: "Depoimento pessoal do representante do(a) reclamado(a) gravado/dispensado"
        depoimento_reclamado_pattern1 = (
            r'Depoimento\s+pessoal\s+do\s+representante\s+d[oa](?:\(a\))?\s+'
            r'reclamad[ao](?:\(a\))?\s+(gravado|dispensado)'
        )
        reclamado_match = re.search(depoimento_reclamado_pattern1, text, re.IGNORECASE)
        if reclamado_match:
            info['depoimento_reclamado'] = reclamado_match.group(1).lower()
            print(f"Depoimento do reclamado: {info['depoimento_reclamado']}")
        
        # Padrão 3: "Depoimento pessoal do(a) reclamado(a) gravado/dispensado" (mais simples)
        if info['depoimento_reclamado'] == 'não mencionado':
            depoimento_reclamado_pattern2 = r'Depoimento\s+pessoal\s+d[oa](?:\(a\))?\s+reclamad[ao](?:\(a\))?\s+(gravado|dispensado)'
            reclamado_match2 = re.search(depoimento_reclamado_pattern2, text, re.IGNORECASE)
            if reclamado_match2:
                info['depoimento_reclamado'] = reclamado_match2.group(1).lower()
                print(f"Depoimento do reclamado (padrão 2): {info['depoimento_reclamado']}")

        # Padrão 4: linha única no plural — "Depoimentos pessoais dos representantes das reclamadas gravado"
        if info['depoimento_reclamado'] == 'não mencionado':
            depoimento_reclamados_plural = re.search(
                r'Depoimentos\s+pessoais\s+dos\s+representantes\s+das?\s+reclamad[ao]s?\s+(gravado|dispensado)',
                text, re.IGNORECASE
            )
            if depoimento_reclamados_plural:
                info['depoimento_reclamado'] = depoimento_reclamados_plural.group(1).lower()
                print(f"Depoimento(s) dos representantes das reclamadas (plural): {info['depoimento_reclamado']}")

        # Padrão 5: "Depoimento pessoal do representante da reclamada gravado" (singular por reclamada)
        if info['depoimento_reclamado'] == 'não mencionado':
            depoimento_repr_reclamada = re.search(
                r'Depoimento\s+pessoal\s+do\s+representante\s+da\s+reclamad[ao]\s+(gravado|dispensado)',
                text, re.IGNORECASE
            )
            if depoimento_repr_reclamada:
                info['depoimento_reclamado'] = depoimento_repr_reclamada.group(1).lower()
                print(f"Depoimento do representante da reclamada: {info['depoimento_reclamado']}")

        # Verifica se informações essenciais foram encontradas
        if not info['juiz'] and not info['reclamante'] and not info['reclamadas']:
             print("Aviso: Nenhuma informação chave (Juiz, Reclamante, Reclamada(s)) foi extraída da ata. A qualidade do pós-processamento pode ser afetada.")
        elif not info['juiz']:
             print("Aviso: Nome do Juiz não encontrado na ata.")
        elif not info['reclamante'] or not info['advogado_reclamante']:
             print("Aviso: Nome do Reclamante ou seu Advogado não encontrado na ata.")
        elif not info['reclamadas'] or not info['advogados_reclamadas']:
             print("Aviso: Nome da Reclamada ou seu Advogado não encontrado na ata.")


        return info
    except FileNotFoundError:
         return f"Erro: Arquivo da ata não encontrado em '{ata_path}'."
    except Exception as e:
        import traceback
        print(f"Erro inesperado ao processar a ata: {e}\n{traceback.format_exc()}")
        return f"Erro inesperado ao extrair informações da ata: {str(e)}"


def get_speaker_identification_known_values(ata_info, max_length=35):
    """Monta a lista de nomes (known_values) para Speaker Identification da AssemblyAI a partir da ata.
    Retorna lista de strings com no máximo max_length caracteres cada (limite da API)."""
    if not isinstance(ata_info, dict) or ata_info.get('error') or ata_info.get('info'):
        return []
    names = []
    for key in ('juiz', 'reclamante', 'advogado_reclamante'):
        val = ata_info.get(key)
        if val and isinstance(val, str) and val.strip():
            s = val.strip()[:max_length]
            if s and s not in names:
                names.append(s)
    for rec in ata_info.get('reclamadas') or []:
        if rec and isinstance(rec, str) and rec.strip():
            s = rec.strip()[:max_length]
            if s and s not in names:
                names.append(s)
    for prep in ata_info.get('prepostos') or []:
        if prep and isinstance(prep, str) and prep.strip() and prep.strip().upper() != "N/I":
            s = prep.strip()[:max_length]
            if s and s not in names:
                names.append(s)
    for adv_entry in ata_info.get('advogados_reclamadas') or []:
        adv_list = adv_entry if isinstance(adv_entry, list) else [adv_entry]
        for adv in adv_list:
            if adv and isinstance(adv, str) and adv.strip():
                s = adv.strip()[:max_length]
                if s and s not in names:
                    names.append(s)
    for t in ata_info.get('testemunhas_reclamante') or []:
        if t and isinstance(t, str) and t.strip():
            s = t.strip()[:max_length]
            if s and s not in names:
                names.append(s)
    for t in ata_info.get('testemunhas_reclamada') or []:
        if t and isinstance(t, str) and t.strip():
            s = t.strip()[:max_length]
            if s and s not in names:
                names.append(s)
    return names


def format_ata_info(ata_info):
    """Formata as informações extraídas da ata para exibição ou uso em prompts."""
    if isinstance(ata_info, str) and ata_info.startswith("Erro"):
        return ata_info # Retorna a mensagem de erro diretamente

    if not isinstance(ata_info, dict):
        return "Erro: Formato inválido das informações da ata recebidas."

    formatted_parts = ["**INFORMAÇÕES EXTRAÍDAS DA ATA DE AUDIÊNCIA (TODOS OS INTERLOCUTORES):**"]

    # Adiciona informações apenas se existirem e não forem None ou vazias/N/I
    if ata_info.get('juiz'):
        formatted_parts.append(f"**Juiz:** {ata_info['juiz']}")
    
    # Informações sobre o reclamante
    if ata_info.get('reclamante'):
        formatted_parts.append(f"**Reclamante:** {ata_info['reclamante']}")
        # Adiciona informação sobre o depoimento do reclamante
        if ata_info.get('depoimento_reclamante'):
            status = ata_info['depoimento_reclamante']
            if status == 'gravado':
                formatted_parts.append(f"  → Depoimento pessoal do reclamante: **GRAVADO**")
            elif status == 'dispensado':
                formatted_parts.append(f"  → Depoimento pessoal do reclamante: **DISPENSADO**")
    
    if ata_info.get('advogado_reclamante'):
        oab_reclamante = ata_info.get('advogado_reclamante_oab')
        if oab_reclamante:
            formatted_parts.append(f"**Advogado do Reclamante:** {ata_info['advogado_reclamante']} ({oab_reclamante})")
        else:
            formatted_parts.append(f"**Advogado do Reclamante:** {ata_info['advogado_reclamante']}")
    
    # Trata múltiplas reclamadas
    num_reclamadas = len(ata_info.get('reclamadas', []))
    for i in range(num_reclamadas):
        if i < len(ata_info.get('reclamadas', [])):
            formatted_parts.append(f"**{i+1}ª Reclamada:** {ata_info['reclamadas'][i]}")
            if i < len(ata_info.get('prepostos', [])) and ata_info['prepostos'][i] != "N/I":
                formatted_parts.append(f"  → Representante/Preposto: {ata_info['prepostos'][i]}")
            advs_entry = ata_info['advogados_reclamadas'][i] if i < len(ata_info.get('advogados_reclamadas', [])) else None
            advs_list = advs_entry if isinstance(advs_entry, list) else ([advs_entry] if advs_entry else [])
            oabs_entry = ata_info.get('advogados_reclamadas_oab', [])[i] if i < len(ata_info.get('advogados_reclamadas_oab', [])) else None
            oabs_list = oabs_entry if isinstance(oabs_entry, list) else ([oabs_entry] if oabs_entry else [])
            for j, adv_nome in enumerate(advs_list, 1):
                if adv_nome:
                    rotulo_adv = "Advogada" if len(advs_list) > 1 else "Advogado"
                    oab_adv = oabs_list[j - 1] if j - 1 < len(oabs_list) else None
                    adv_texto = f"{adv_nome} ({oab_adv})" if oab_adv else adv_nome
                    if len(advs_list) > 1:
                        formatted_parts.append(f"  → {rotulo_adv} {j}: {adv_texto}")
                    else:
                        formatted_parts.append(f"  → {rotulo_adv}: {adv_texto}")
            # Depoimento do representante (na ata costuma constar uma única linha para o polo reclamado)
            if i == 0 and ata_info.get('depoimento_reclamado'):
                status = ata_info['depoimento_reclamado']
                if status == 'gravado':
                    formatted_parts.append(
                        "  → Depoimento pessoal do representante da reclamada (polo passivo): **GRAVADO**"
                    )
                elif status == 'dispensado':
                    formatted_parts.append(
                        "  → Depoimento pessoal do representante da reclamada (polo passivo): **DISPENSADO**"
                    )

    # Trata testemunhas do reclamante
    if ata_info.get('testemunhas_reclamante'):
        formatted_parts.append("**Testemunhas do Reclamante:**")
        for i, testemunha in enumerate(ata_info['testemunhas_reclamante'], 1):
            numero = ata_info.get('testemunhas_reclamante_numeros', [])[i - 1] if i - 1 < len(ata_info.get('testemunhas_reclamante_numeros', [])) else i
            status = ata_info.get('testemunhas_reclamante_status', [])[i - 1] if i - 1 < len(ata_info.get('testemunhas_reclamante_status', [])) else None
            if status == 'gravado':
                formatted_parts.append(f"  → {numero}ª Testemunha: {testemunha} - **DEPOIMENTO GRAVADO**")
            elif status == 'dispensado':
                formatted_parts.append(f"  → {numero}ª Testemunha: {testemunha} - **DEPOIMENTO DISPENSADO**")
            else:
                formatted_parts.append(f"  → {numero}ª Testemunha: {testemunha}")

    # Trata testemunhas da reclamada
    if ata_info.get('testemunhas_reclamada'):
        formatted_parts.append("**Testemunhas da Reclamada:**")
        for i, testemunha in enumerate(ata_info['testemunhas_reclamada'], 1):
            numero = ata_info.get('testemunhas_reclamada_numeros', [])[i - 1] if i - 1 < len(ata_info.get('testemunhas_reclamada_numeros', [])) else i
            status = ata_info.get('testemunhas_reclamada_status', [])[i - 1] if i - 1 < len(ata_info.get('testemunhas_reclamada_status', [])) else None
            if status == 'gravado':
                formatted_parts.append(f"  → {numero}ª Testemunha: {testemunha} - **DEPOIMENTO GRAVADO**")
            elif status == 'dispensado':
                formatted_parts.append(f"  → {numero}ª Testemunha: {testemunha} - **DEPOIMENTO DISPENSADO**")
            else:
                formatted_parts.append(f"  → {numero}ª Testemunha: {testemunha}")

    # Se nenhuma informação foi adicionada além do título inicial
    if len(formatted_parts) == 1 and "error" not in ata_info and "info" not in ata_info:
         # Se não houve erro explícito nem info, mas o dicionário está vazio
         return "Nenhuma informação relevante (Juiz, Partes, Advogados, Testemunhas) encontrada na ata."
    elif "error" in ata_info:
         return ata_info["error"] # Retorna a mensagem de erro original da extração
    elif "info" in ata_info and len(formatted_parts) == 1:
         return ata_info["info"] # Retorna a mensagem informativa (ex: "Nenhuma ata fornecida")

    return "\n".join(formatted_parts)

# --- Funções de Pós-Processamento (create_post_processing_prompt, process_transcript_with_claude, etc.) ---
# (Mantidas como na versão anterior, sem alterações significativas aqui)
def create_post_processing_prompt(ata_info_formatted, transcript_text_chunk=None):
    """Cria o prompt padrão para os modelos de LLM realizarem o pós-processamento."""
    # Verifica se a formatação da ata resultou em erro ou aviso
    if "Erro:" in ata_info_formatted or "Nenhuma informação relevante" in ata_info_formatted or "Nenhuma ata fornecida" in ata_info_formatted:
         ata_section = f"**Atenção:** Informações da ata ausentes ou incompletas:\n{ata_info_formatted}\n\n**Instrução:** Proceda com a identificação dos interlocutores baseando-se **primariamente** no contexto da conversa e nas regras processuais descritas abaixo. Use rótulos genéricos como 'Juiz', 'Reclamante', 'Advogado Reclamante', 'Preposto 1ª Reclamada', 'Advogado 1ª Reclamada', 'Testemunha Reclamante 1', etc."
    else:
         ata_section = f"**INFORMAÇÕES DA ATA DE AUDIÊNCIA (use como base para os nomes e IDENTIFIQUE TODOS OS INTERLOCUTORES):**\n{ata_info_formatted}"

    # Define os rótulos a serem usados, adaptando para múltiplas reclamadas/testemunhas
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

A transcrição original foi gerada por IA e pode conter:
- Identificadores genéricos como "Interlocutor A", "Interlocutor B", etc.
- Identificadores como "Interlocutor Desconhecido" ou "Interlocutor Gemini"
- Possíveis erros na atribuição de falas, especialmente em:
  * Falas curtas
  * Interrupções
  * Momentos de sobreposição de vozes
  * Início/fim de depoimentos

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
   * O arquivo de saída DEVE ser a transcrição completa com os rótulos genéricos substituídos por nomes/cargos da ata
   * Substitua "Interlocutor Soniox", "Interlocutor Gemini", "Interlocutor OpenAI", "Interlocutor A/B/C" e semelhantes por "Juiz: NOME", "Reclamante: NOME", "Representante/Preposto da Reclamada: NOME", "Advogado(a): NOME" ou "Testemunha: NOME", conforme a ata e o contexto
   * Use os nomes EXATOS da ata quando disponíveis
   * Siga a ordem processual para identificar interlocutores
   * **CRÍTICO**: Não confunda testemunhas com partes
   * **CRÍTICO**: Identifique corretamente quem faz perguntas a quem
   * Use "Interlocutor Não Identificado" apenas quando for impossível identificar, após aplicar a ata e a ordem processual

3. **FORMATAÇÃO:**
   * Mantenha timestamps originais se presentes
   * Use o formato: [HH:MM:SS] INTERLOCUTOR: Texto
   * Não adicione timestamps se não existirem no original
   * Não adicione títulos ou seções extras
   * Não devolva a transcrição com os rótulos genéricos originais quando a ata permitir identificação

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

    return prompt.strip()

def process_transcript_with_claude(transcript_path, ata_info, api_key, output_path=None, model_name="claude-3-7-sonnet-latest"):
    """Processa a transcrição usando a API do Anthropic Claude."""
    # (Código da função mantido como na versão anterior)
    try:
        if not api_key:
            return "Erro: API Key do Claude não fornecida."
        if not os.path.exists(transcript_path):
             return f"Erro: Arquivo de transcrição não encontrado para processamento Claude: {transcript_path}"

        with open(transcript_path, 'r', encoding='utf-8') as file:
            transcript_text = file.read()

        if not transcript_text.strip():
            return f"Erro: O arquivo de transcrição '{os.path.basename(transcript_path)}' está vazio."

        ata_info_formatted = format_ata_info(ata_info) # Formata as informações da ata
        prompt = create_post_processing_prompt(ata_info_formatted, transcript_text) # Usa a função base

        # Definindo timeout explícito de 15 minutos (900s) para evitar problemas em arquivos grandes
        client = anthropic.Anthropic(api_key=api_key, timeout=900.0)
        if output_path:
            new_file_path = output_path
        else:
            base_name = os.path.basename(transcript_path)
            base_name = base_name.replace("_transcrito", "")
            new_file_name = os.path.splitext(base_name)[0] + "_formatado_claude.txt" # Nomeia especificamente
            new_file_path = os.path.join(os.path.dirname(transcript_path), new_file_name)

        # Defina um tamanho máximo de tokens adequado (Claude 3.7 Sonnet suporta 200k)
        max_tokens_to_sample = 64000 # Máximo permitido pelo modelo

        print(f"Enviando prompt para o Claude (Modelo: {model_name})...")
        start_claude_time = time.time()
        processed_text = ""
        with client.messages.stream(
            model=model_name,
            max_tokens=max_tokens_to_sample,
            temperature=0.0,
            system="Você é um assistente especialista em Direito Processual do Trabalho brasileiro focado em corrigir a identificação de interlocutores em transcrições de audiências, seguindo regras processuais e informações da ata.",
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                processed_text += text
        end_claude_time = time.time()
        print(f"Claude respondeu em {end_claude_time - start_claude_time:.2f} segundos.")

        if not processed_text.strip():
             return f"Erro ao processar com Claude: Nenhuma resposta de texto recebida. Verifique o console para possíveis logs de erro da API."

        # Salva o resultado
        with open(new_file_path, 'w', encoding='utf-8') as output_file:
            output_file.write(processed_text.strip()) # Remove espaços extras no fim

        print(f"Processamento com Claude concluído. Arquivo salvo em: {new_file_path}")
        return new_file_path

    except anthropic.APIConnectionError as e:
         return f"Erro de conexão com a API do Claude: Verifique sua rede. Detalhes: {e}"
    except anthropic.RateLimitError as e:
         return f"Erro de limite de taxa com a API do Claude: Aguarde e tente novamente. Detalhes: {e}"
    except anthropic.AuthenticationError as e:
         return f"Erro de autenticação com a API do Claude: Verifique sua API Key. Detalhes: {e}"
    except anthropic.APIStatusError as e:
         return f"Erro na API do Claude (Status: {e.status_code}): {e.message}"
    except FileNotFoundError:
         # Já tratado no início, mas para garantir
         return f"Erro interno: Arquivo de transcrição não encontrado em '{transcript_path}' ao tentar processar com Claude."
    except Exception as e:
        import traceback
        print(f"Erro inesperado no processamento com Claude:\n{traceback.format_exc()}")
        return f"Erro inesperado ao processar com Claude: {str(e)}"

def process_transcript_with_openai(transcript_path, ata_info, api_key, output_path=None, model_to_use="gpt-4o-mini"):
    """Processa a transcrição usando a API OpenAI (GPT)."""
    # (Código da função mantido como na versão anterior)
    try:
        if not api_key:
            return "Erro: API Key do OpenAI não fornecida."
        if not os.path.exists(transcript_path):
             return f"Erro: Arquivo de transcrição não encontrado para processamento OpenAI: {transcript_path}"

        # Ler o arquivo de transcrição
        with open(transcript_path, 'r', encoding='utf-8') as file:
            transcript_text = file.read()

        if not transcript_text.strip():
            return f"Erro: O arquivo de transcrição '{os.path.basename(transcript_path)}' está vazio."

        ata_info_formatted = format_ata_info(ata_info) # Formata as informações da ata

        # Usar um modelo com janela de contexto grande para evitar chunking
        # Timeout explícito de 15 min (900s)
        client = OpenAI(api_key=api_key, timeout=900.0)
        print(f"Usando modelo OpenAI: {model_to_use}")

        prompt = create_post_processing_prompt(ata_info_formatted, transcript_text) # Usa a função base

        if output_path:
            new_file_path = output_path
        else:
            base_name = os.path.basename(transcript_path)
            base_name = base_name.replace("_transcrito", "")
            new_file_name = os.path.splitext(base_name)[0] + "_formatado_openai.txt" # Nomeia especificamente
            new_file_path = os.path.join(os.path.dirname(transcript_path), new_file_name)

        print(f"Enviando prompt para OpenAI (Modelo: {model_to_use}). Tamanho do texto: {len(transcript_text)} caracteres.")
        start_openai_time = time.time()

        # Wrap everything in a try block to use existing exception handlers at the end
        try:
            # Retry logic for connection issues
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    response = client.chat.completions.create(
                        model=model_to_use,
                        messages=[
                             {"role": "system", "content": "Você é um assistente especialista em Direito Processual do Trabalho brasileiro focado em corrigir a identificação de interlocutores em transcrições de audiências, seguindo regras processuais e informações da ata."},
                             {"role": "user", "content": prompt}
                             ],
                        temperature=0, # Determinístico
                    )
                    break # Sucesso
                except openai.APIConnectionError as e:
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = 2 * retry_count
                        print(f"Erro de conexão OpenAI (Tentativa {retry_count}/{max_retries}). Aguardando {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise e # Re-raise to be caught by outer except

            end_openai_time = time.time()
            print(f"OpenAI respondeu em {end_openai_time - start_openai_time:.2f} segundos.")


            processed_text = response.choices[0].message.content

            if not processed_text or not processed_text.strip():
                finish_reason = response.choices[0].finish_reason
                print(f"Resposta do OpenAI vazia ou inválida. Finish reason: {finish_reason}")
                if finish_reason == 'length':
                        return f"Erro ao processar com OpenAI ({model_to_use}): A resposta foi truncada. O resultado pode estar incompleto."
                elif finish_reason == 'content_filter':
                        return f"Erro ao processar com OpenAI ({model_to_use}): O conteúdo foi bloqueado pelo filtro de segurança."
                else:
                        return f"Erro ao processar com OpenAI ({model_to_use}): Nenhuma resposta de texto recebida (Finish reason: {finish_reason})."


            with open(new_file_path, 'w', encoding='utf-8') as output_file:
                output_file.write(processed_text.strip()) # Remove espaços extras

            print(f"Processamento com OpenAI concluído. Arquivo salvo em: {new_file_path}")
            return new_file_path

        except openai.BadRequestError as e:
             if hasattr(e, 'code') and e.code == 'context_length_exceeded':
                  print(f"Erro: O prompt excedeu o limite de contexto do modelo {model_to_use}. A transcrição é muito longa para este modelo.")
                  return f"Erro: Transcrição muito longa para o modelo {model_to_use}. Tente um modelo com maior capacidade ou divida o áudio."
             else:
                  print(f"Erro na requisição OpenAI (Bad Request): {e}")
                  return f"Erro na requisição OpenAI: {str(e)}"
        except openai.AuthenticationError as e:
             return f"Erro de autenticação com a API OpenAI: Verifique sua API Key. ({e})"
        except openai.RateLimitError as e:
             return f"Erro de limite de taxa com a API OpenAI: Aguarde e tente novamente. ({e})"
        except openai.APIConnectionError as e:
             return f"Erro de conexão com a API OpenAI: Verifique sua rede. ({e})"
        except openai.APIStatusError as e:
             return f"Erro na API OpenAI (Status: {e.status_code}): {e.message}"
        except FileNotFoundError:
            return f"Erro interno: Arquivo de transcrição não encontrado em '{transcript_path}' ao tentar processar com OpenAI."
        except Exception as e:
            import traceback
            print(f"Erro inesperado no processamento com OpenAI:\n{traceback.format_exc()}")
            return f"Erro inesperado ao processar com OpenAI: {str(e)}"

    except Exception as e:
        return f"Erro geral ao iniciar processamento com OpenAI: {str(e)}"

def process_transcript_with_openrouter(transcript_path, ata_info, api_key, output_path=None, model_to_use="openai/gpt-4o-mini"):
    """Processa a transcrição usando a API OpenRouter (chat completions)."""
    try:
        if not api_key:
            return "Erro: API Key do OpenRouter não fornecida."
        if not os.path.exists(transcript_path):
            return f"Erro: Arquivo de transcrição não encontrado para processamento OpenRouter: {transcript_path}"

        with open(transcript_path, 'r', encoding='utf-8') as file:
            transcript_text = file.read()

        if not transcript_text.strip():
            return f"Erro: O arquivo de transcrição '{os.path.basename(transcript_path)}' está vazio."

        ata_info_formatted = format_ata_info(ata_info)
        prompt = create_post_processing_prompt(ata_info_formatted, transcript_text)

        if output_path:
            new_file_path = output_path
        else:
            base_name = os.path.basename(transcript_path)
            base_name = base_name.replace("_transcrito", "")
            new_file_name = os.path.splitext(base_name)[0] + "_formatado_openrouter.txt"
            new_file_path = os.path.join(os.path.dirname(transcript_path), new_file_name)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://kiwiscribe.local",
            "X-Title": "Kiwiscribe",
        }
        payload = {
            "model": model_to_use,
            "messages": [
                {
                    "role": "system",
                    "content": "Você é um assistente especialista em Direito Processual do Trabalho brasileiro focado em corrigir a identificação de interlocutores em transcrições de audiências, seguindo regras processuais e informações da ata."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0,
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=900,
        )
        response.raise_for_status()
        response_json = response.json() or {}

        choices = response_json.get('choices') or []
        if not choices:
            return f"Erro ao processar com OpenRouter: resposta sem escolhas. Detalhes: {response_json}"

        message = (choices[0].get('message') or {})
        content = message.get('content')
        if isinstance(content, list):
            processed_text = "".join(part.get('text', '') for part in content if isinstance(part, dict))
        else:
            processed_text = content or ""

        if not processed_text.strip():
            return "Erro ao processar com OpenRouter: resposta sem conteúdo textual."

        with open(new_file_path, 'w', encoding='utf-8') as output_file:
            output_file.write(processed_text.strip())

        return new_file_path

    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            detail = e.response.text if e.response is not None else ""
        except Exception:
            detail = ""
        return f"Erro HTTP da API OpenRouter: {e}. {detail}"
    except requests.exceptions.RequestException as e:
        return f"Erro de conexão com a API OpenRouter: {e}"
    except Exception as e:
        import traceback
        print(f"Erro inesperado no processamento com OpenRouter:\n{traceback.format_exc()}")
        return f"Erro inesperado ao processar com OpenRouter: {str(e)}"

def process_transcript_with_gemini(transcript_path, ata_info, api_key_gemini, output_path=None, status_callback=None, model_name="gemini-2.5-flash"):
    """Processa a transcrição usando a API do Google Gemini."""
    try:
        def _emit_status(message):
            print(message)
            if status_callback:
                try:
                    status_callback(message)
                except Exception:
                    pass

        # Configurar API Key
        if not api_key_gemini:
            return "Erro: API Key do Gemini não fornecida."
            
        print("Usando API Key do Gemini para pós-processamento.")

        if not os.path.exists(transcript_path):
             return f"Erro: Arquivo de transcrição não encontrado para processamento Gemini: {transcript_path}"

        # Ler o arquivo de transcrição
        with open(transcript_path, 'r', encoding='utf-8') as file:
            transcript_text = file.read()

        if not transcript_text.strip():
            return f"Erro: O arquivo de transcrição '{os.path.basename(transcript_path)}' está vazio."

        # Usar REST API direta para evitar problemas com timeout do SDK
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key_gemini}"
        headers = {'Content-Type': 'application/json'}

        def _extract_gemini_text(response_json):
            candidates = response_json.get('candidates') or []
            if not candidates:
                return "", f"Resposta sem candidates: {response_json}"
            candidate = candidates[0]
            parts = (candidate.get('content') or {}).get('parts') or []
            text_parts = [part.get('text', '') for part in parts if part.get('text')]
            if text_parts:
                return ''.join(text_parts), None
            finish_reason = candidate.get('finishReason') or 'sem finishReason'
            safety = candidate.get('safetyRatings') or response_json.get('promptFeedback') or ''
            return "", f"Resposta sem texto. finishReason={finish_reason}; safety/promptFeedback={safety}"

        def _request_gemini(prompt_text, label):
            data = {
                "contents": [{
                    "parts": [{"text": prompt_text}]
                }],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 16384
                }
            }
            max_retries = 3
            last_error = ""
            for attempt in range(1, max_retries + 1):
                attempt_start = time.time()
                try:
                    _emit_status(f"Gemini: enviando {label} (tentativa {attempt}/{max_retries}, prompt {len(prompt_text)} caracteres).")
                    response = requests.post(url, headers=headers, json=data, timeout=900)
                    duration = time.time() - attempt_start
                    if response.status_code == 200:
                        response_json = response.json()
                        text, parse_error = _extract_gemini_text(response_json)
                        if text.strip():
                            _emit_status(f"Gemini: {label} concluído em {duration:.2f}s.")
                            return text, None
                        last_error = parse_error or "Resposta sem texto."
                        _emit_status(f"Gemini: {label} retornou sem texto em {duration:.2f}s. {last_error}")
                    else:
                        body = response.text[:1000]
                        last_error = f"Status {response.status_code}: {body}"
                        _emit_status(f"Gemini: erro em {label} ({last_error})")
                except requests.exceptions.Timeout:
                    duration = time.time() - attempt_start
                    last_error = f"timeout após {duration:.2f}s"
                    _emit_status(f"Gemini: timeout em {label} (tentativa {attempt}/{max_retries}, {duration:.2f}s).")
                except Exception as e:
                    duration = time.time() - attempt_start
                    last_error = f"{type(e).__name__}: {e}"
                    _emit_status(f"Gemini: erro em {label} (tentativa {attempt}/{max_retries}, {duration:.2f}s): {e}")
                if attempt < max_retries:
                    time.sleep(2)
            return "", last_error or "erro não especificado"

        def _split_transcript_for_gemini(text, ata_formatted, max_prompt_chars=24000):
            lines = text.splitlines(True)
            chunks = []
            current = []
            current_len = 0
            prompt_overhead = len(create_post_processing_prompt(ata_formatted, ""))
            max_chars = max(8000, max_prompt_chars - prompt_overhead)
            for line in lines:
                if current and current_len + len(line) > max_chars:
                    chunks.append(''.join(current))
                    current = [line]
                    current_len = len(line)
                else:
                    current.append(line)
                    current_len += len(line)
            if current:
                chunks.append(''.join(current))
            return chunks

        ata_info_formatted = format_ata_info(ata_info)
        start_gemini_time = time.time()
        response_text = ""
        prompt = create_post_processing_prompt(ata_info_formatted, transcript_text)

        # Prompts maiores têm causado RemoteDisconnected por volta de 60s.
        # Mantemos cada requisição menor e previsível.
        if len(prompt) <= 24000:
            response_text, request_error = _request_gemini(prompt, "transcrição completa")
        else:
            max_prompt_chars = 24000
            chunks = _split_transcript_for_gemini(transcript_text, ata_info_formatted, max_prompt_chars=max_prompt_chars)
            _emit_status(
                f"Gemini: transcrição longa ({len(transcript_text)} caracteres). "
                f"Pós-processando em {len(chunks)} partes (limite ~{max_prompt_chars} caracteres por prompt)."
            )
            processed_chunks = []
            request_error = ""
            partial_path = None
            if output_path:
                partial_base, partial_ext = os.path.splitext(output_path)
                partial_path = f"{partial_base}_parcial{partial_ext or '.txt'}"
            for index, chunk in enumerate(chunks, 1):
                chunk_prompt = create_post_processing_prompt(ata_info_formatted, chunk)
                chunk_text, chunk_error = _request_gemini(chunk_prompt, f"parte {index}/{len(chunks)}")
                if not chunk_text.strip():
                    request_error = f"parte {index}/{len(chunks)} falhou: {chunk_error}"
                    break
                processed_chunks.append(chunk_text.strip())
                if partial_path:
                    with open(partial_path, 'w', encoding='utf-8') as partial_file:
                        partial_file.write("\n".join(processed_chunks).strip())
                    _emit_status(f"Gemini: progresso salvo em {os.path.basename(partial_path)} ({index}/{len(chunks)} partes).")
            if processed_chunks and not request_error:
                response_text = "\n".join(processed_chunks)
                if partial_path and os.path.exists(partial_path):
                    try:
                        os.remove(partial_path)
                    except Exception:
                        pass

        if not response_text:
             return f"Erro persistente na API do Gemini. Detalhe: {request_error}"

        end_gemini_time = time.time()
        print(f"Gemini ({model_name}) respondeu em {end_gemini_time - start_gemini_time:.2f} segundos.")
        
        processed_text = response_text.strip()
        
        if not processed_text:
            return f"Erro: O processamento com Gemini ({model_name}) retornou um texto vazio."

        # Salvar o resultado com o nome do modelo
        if output_path:
            new_file_path = output_path
        else:
            base_name = os.path.basename(transcript_path)
            base_name = base_name.replace("_transcrito", "")
            model_suffix = model_name.replace('/', '_').replace(':', '_')
            new_file_name = os.path.splitext(base_name)[0] + f"_formatado_gemini_{model_suffix}.txt"
            new_file_path = os.path.join(os.path.dirname(transcript_path), new_file_name)

        with open(new_file_path, 'w', encoding='utf-8') as output_file:
            output_file.write(processed_text)

        print(f"Processamento com Gemini ({model_name}) concluído. Arquivo salvo em: {new_file_path}")
        return new_file_path

    except FileNotFoundError:
        return f"Erro interno: Arquivo de transcrição não encontrado em '{transcript_path}' ao tentar processar com Gemini."
    except Exception as e:
        import traceback
        print(f"Erro inesperado no processamento com Gemini:\n{traceback.format_exc()}")
        return f"Erro inesperado ao processar com Gemini: {str(e)}"


# --- Diálogo de Seleção de Arquivo (FileTableDialog) ---
# (Mantido como na versão anterior)
class FileTableDialog(QDialog):
    """Diálogo para selecionar arquivos de uma lista (áudio ou ata)."""
    def __init__(self, files, file_type, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Selecionar Arquivo {'de Áudio' if file_type == 'audio' else 'da Ata'}")
        self.setMinimumSize(700, 450)
        self.selected_file = None
        self.current_dir = get_download_dir()  # Diretório inicial

        layout = QVBoxLayoutDialog(self)

        # Botões de ordenação e navegação
        top_buttons = QHBoxLayout()
        
        # Botão para mudar diretório
        change_dir_btn = QPushButton("📁 Mudar Pasta...")
        change_dir_btn.clicked.connect(self.change_directory)
        top_buttons.addWidget(change_dir_btn)
        
        # Botões de ordenação
        sort_name_btn = QPushButton("Nome ↑")
        sort_name_btn.clicked.connect(lambda: self.sort_files("name"))
        sort_date_btn = QPushButton("Data ↑")
        sort_date_btn.clicked.connect(lambda: self.sort_files("date"))
        top_buttons.addWidget(sort_name_btn)
        top_buttons.addWidget(sort_date_btn)
        
        top_buttons.addStretch()
        layout.addLayout(top_buttons)

        # Tabela de arquivos
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Nome do Arquivo", "Data de Modificação"])
        header = self.table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        vertical_header = self.table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        self.table.setAlternatingRowColors(True)

        # Preencher tabela inicial
        self.update_file_list(files)

        # Estilo da tabela
        self.table.setStyleSheet("""
            QTableWidget { gridline-color: #dcdcdc; }
            QTableWidget::item:selected { background-color: #a8c7fa; color: black; }
            QTableWidget::item:hover { background-color: #e6f0ff; }
            QHeaderView::section { background-color: #e8e8e8; padding: 4px; border: 1px solid #c0c0c0; font-weight: bold;}
            QTableWidget QTableCornerButton::section { background-color: #e8e8e8; border: 1px solid #c0c0c0; }
        """)

        layout.addWidget(self.table)

        # Botões de ação
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        cancel_btn = QPushButton("Cancelar")
        self.select_btn = QPushButton("Selecionar")
        self.select_btn.setDefault(True)
        self.select_btn.setEnabled(False)
        cancel_btn.clicked.connect(self.reject)
        self.select_btn.clicked.connect(self.accept_selection)
        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(self.select_btn)
        layout.addLayout(buttons_layout)

        self.setLayout(layout)

        # Conecta eventos
        self.table.itemDoubleClicked.connect(self.accept_selection)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)

    def change_directory(self):
        """Permite ao usuário selecionar um novo diretório."""
        new_dir = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta",
            self.current_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        if new_dir:
            self.current_dir = new_dir
            try:
                files = [f for f in os.listdir(new_dir) if os.path.isfile(os.path.join(new_dir, f))]
                self.update_file_list(files)
            except Exception as e:
                QMessageBox.warning(self, "Erro", f"Erro ao listar arquivos: {str(e)}")

    def sort_files(self, sort_by):
        """Ordena os arquivos por nome ou data."""
        row_count = self.table.rowCount()
        items = []
        
        for row in range(row_count):
            name_item = self.table.item(row, 0)
            date_item = self.table.item(row, 1)
            name = name_item.text() if name_item is not None else ""
            date = date_item.text() if date_item is not None else "01/01/1970 00:00:00"
            items.append((name, date))
        
        if sort_by == "name":
            items.sort(key=lambda x: x[0].lower())
        else:  # sort_by == "date"
            items.sort(key=lambda x: datetime.strptime(x[1], '%d/%m/%Y %H:%M:%S'), reverse=True)
        
        # Atualiza a tabela com os itens ordenados
        for row, (name, date) in enumerate(items):
            name_item = self.table.item(row, 0)
            date_item = self.table.item(row, 1)
            if name_item is not None:
                name_item.setText(name)
            if date_item is not None:
                date_item.setText(date)

    def update_file_list(self, files):
        """Atualiza a lista de arquivos na tabela."""
        self.table.setRowCount(len(files))
        try:
            files_with_mtime = []
            for f in files:
                file_path = os.path.join(self.current_dir, f)
                try:
                    mtime = os.path.getmtime(file_path)
                    files_with_mtime.append((f, mtime))
                except FileNotFoundError:
                    continue

            # Ordena por data (mais recentes primeiro)
            sorted_files = sorted(files_with_mtime, key=lambda x: x[1], reverse=True)

            for row, (f, mtime) in enumerate(sorted_files):
                name_item = QTableWidgetItem(f)
                name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                name_item.setToolTip(f)

                date_str = datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M:%S')
                date_item = QTableWidgetItem(date_str)
                date_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

                self.table.setItem(row, 0, name_item)
                self.table.setItem(row, 1, date_item)

        except Exception as e:
            print(f"Erro ao ordenar arquivos: {e}")

    def on_selection_changed(self):
        """Habilita o botão 'Selecionar' se uma linha estiver selecionada."""
        self.select_btn.setEnabled(len(self.table.selectedItems()) > 0)

    def accept_selection(self):
        """Armazena o arquivo selecionado e fecha o diálogo com 'Accepted'."""
        selected_items = self.table.selectedItems()
        if selected_items:
            self.selected_file = os.path.join(self.current_dir, selected_items[0].text())
            self.accept()
        else:
            self.reject()

    def get_selected_file(self):
        """Retorna o caminho completo do arquivo selecionado."""
        return self.selected_file

# --- Classe de Sinais (WorkerSignals) ---
# (Mantida como na versão anterior)
class WorkerSignals(QObject):
    message = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

# --- Classe Principal da Janela (TranscriptionWindow) ---
class TranscriptionWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.logo_image_path = os.path.join(self.app_dir, "KiwiScribeSquared.png")
        self.installer_icon_path = os.path.join(self.app_dir, "KiwiScribeSquared.ico")

        self.setWindowTitle("Transcrição e Pós-Processamento de Audiências Trabalhistas")
        self.setMinimumSize(850, 750)
        if os.path.exists(self.installer_icon_path):
            self.setWindowIcon(QIcon(self.installer_icon_path))
        elif os.path.exists(self.logo_image_path):
            self.setWindowIcon(QIcon(self.logo_image_path))
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

        top_section_widget = QWidget()
        top_section_layout = QHBoxLayout(top_section_widget)
        top_section_layout.setContentsMargins(0, 0, 0, 0)
        top_section_layout.setSpacing(10)

        left_section_widget = QWidget()
        left_section_layout = QVBoxLayout(left_section_widget)
        left_section_layout.setContentsMargins(0, 0, 0, 0)
        left_section_layout.setSpacing(2)

        # --- 1. Serviço de Transcrição --- MODIFICADO
        service_group = QWidget()
        service_group_layout = QVBoxLayout(service_group)
        service_group_layout.setContentsMargins(0, 0, 0, 0)
        service_group_layout.setSpacing(2)

        service_layout = QVBoxLayout()
        service_layout.setContentsMargins(0, 0, 0, 0)
        service_row1 = QHBoxLayout()
        service_row1.setContentsMargins(0, 0, 0, 0)
        service_row2 = QHBoxLayout()
        service_row2.setContentsMargins(22, 0, 0, 0)
        service_label = QLabel("<b>1. Serviço de Transcrição:</b>")
        self.service_assembly = QRadioButton("AssemblyAI")
        self.service_openai = QRadioButton("Open AI")
        self.service_gemini = QRadioButton("Google")
        self.service_openrouter = QRadioButton("OpenRouter")
        self.service_soniox = QRadioButton("Soniox")
        self.service_just_post_process = QRadioButton("Apenas Pós-processar (Txt Local)") # NOVO: Opção apenas pós-processar
        self.service_just_docx = QRadioButton("Apenas Gerar DOCX (Txt Local)")
        self.service_assembly.setChecked(True) # Padrão
        service_row1.addWidget(service_label)
        service_row1.addWidget(self.service_assembly)
        service_row1.addWidget(self.service_openai)
        service_row1.addWidget(self.service_gemini)
        service_row1.addWidget(self.service_openrouter)
        service_row1.addStretch()
        service_row2.addWidget(self.service_soniox)
        service_row2.addWidget(self.service_just_post_process)
        service_row2.addWidget(self.service_just_docx)
        service_row2.addStretch()
        service_layout.addLayout(service_row1)
        service_layout.addLayout(service_row2)
        service_group_layout.addLayout(service_layout)

        transcription_model_group = QHBoxLayout()
        transcription_model_group.setContentsMargins(22, 0, 0, 0)
        transcription_model_label = QLabel("Modelo de transcrição:")
        self.transcription_model_combo = QComboBox()
        self.transcription_model_combo.setToolTip("Lista filtrada para modelos/serviços capazes de trabalhar com áudio ou transcrição local.")
        transcription_model_group.addWidget(transcription_model_label)
        transcription_model_group.addWidget(self.transcription_model_combo)
        transcription_model_group.addStretch()
        service_group_layout.addLayout(transcription_model_group)
        left_section_layout.addWidget(service_group)

        logo_panel = QWidget()
        logo_panel_layout = QVBoxLayout(logo_panel)
        logo_panel_layout.setContentsMargins(0, 0, 0, 0)
        logo_panel_layout.setSpacing(0)
        logo_panel.setFixedWidth(110)

        logo_panel_layout.addStretch()
        if os.path.exists(self.logo_image_path):
            top_logo_label = QLabel()
            top_logo_pixmap = QPixmap(self.logo_image_path)
            if not top_logo_pixmap.isNull():
                top_logo_label.setPixmap(
                    top_logo_pixmap.scaled(
                        92,
                        92,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                top_logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                top_logo_label.setToolTip("KiwiScribe")
                logo_panel_layout.addWidget(top_logo_label)
        logo_panel_layout.addStretch()

        top_section_layout.addWidget(left_section_widget, 1)
        top_section_layout.addWidget(logo_panel, 0)
        controls_layout.addWidget(top_section_widget)

        # --- 2. Arquivos de Entrada ---
        # (Layout mantido como antes)
        file_input_group = QWidget()
        file_input_layout = QVBoxLayout(file_input_group)
        file_input_layout.setContentsMargins(0, 5, 0, 5)
        file_input_label = QLabel("<b>2. Arquivos de Entrada:</b>")
        file_input_layout.addWidget(file_input_label)
        # Arquivo de áudio
        audio_group = QHBoxLayout()
        audio_label = QLabel("Áudio:")
        self.audio_input = QLineEdit()
        self.audio_input.setPlaceholderText("Selecione ou cole o caminho/URL do áudio")
        audio_browse_btn = QPushButton("Procurar...")
        audio_browse_btn.setToolTip("Procurar arquivo de áudio local (.mp3, .wav, .m4a, etc.)")
        audio_browse_btn.clicked.connect(lambda: self.browse_file_dialog('audio')) # Usa o novo diálogo
        audio_group.addWidget(audio_label)
        audio_group.addWidget(self.audio_input)
        audio_group.addWidget(audio_browse_btn)
        self.audio_group_container = QWidget() # Container para poder esconder o grupo todo
        audio_group_layout = QVBoxLayout(self.audio_group_container)
        audio_group_layout.setContentsMargins(0,0,0,0)
        audio_group_layout.addLayout(audio_group)
        file_input_layout.addWidget(self.audio_group_container)

        # Arquivo de Transcrição (Apenas para modo "Apenas Pós-processar")
        transcription_group = QHBoxLayout()
        transcription_label = QLabel("Transcrição (txt):")
        self.transcription_input = QLineEdit()
        self.transcription_input.setPlaceholderText("Selecione o arquivo de texto com a transcrição prévia")
        transcription_browse_btn = QPushButton("Procurar...")
        transcription_browse_btn.setToolTip("Procurar arquivo de texto (.txt)")
        transcription_browse_btn.clicked.connect(lambda: self.browse_file_dialog('transcription'))
        transcription_group.addWidget(transcription_label)
        transcription_group.addWidget(self.transcription_input)
        transcription_group.addWidget(transcription_browse_btn)
        
        self.transcription_group_container = QWidget() # Container para mostrar/esconder
        transcription_group_layout = QVBoxLayout(self.transcription_group_container)
        transcription_group_layout.setContentsMargins(0,0,0,0)
        transcription_group_layout.addLayout(transcription_group)
        file_input_layout.addWidget(self.transcription_group_container)
        # Arquivo da ata
        ata_group = QHBoxLayout()
        ata_label = QLabel("Ata:")
        self.ata_input = QLineEdit()
        self.ata_input.setPlaceholderText("Opcional: Selecione o arquivo da ata (.pdf, .txt) para melhor identificação")
        ata_browse_btn = QPushButton("Procurar...")
        ata_browse_btn.setToolTip("Procurar arquivo da ata em formato PDF ou TXT")
        ata_browse_btn.clicked.connect(lambda: self.browse_file_dialog('ata')) # Usa o novo diálogo
        ata_group.addWidget(ata_label)
        ata_group.addWidget(self.ata_input)
        ata_group.addWidget(ata_browse_btn)
        file_input_layout.addLayout(ata_group)
        controls_layout.addWidget(file_input_group)

        # --- Parâmetros Específicos (Nº Interlocutores) ---
        # (Layout mantido como antes, controlado por update_ui_visibility)
        params_group = QHBoxLayout()
        params_group.setContentsMargins(0, 5, 0, 5)
        self.num_container = QWidget() # Container para mostrar/esconder
        num_layout = QHBoxLayout(self.num_container)
        num_layout.setContentsMargins(0,0,0,0)
        num_label = QLabel("Nº Interlocutores (AssemblyAI):")
        self.num_input = QLineEdit("0")
        self.num_input.setInputMask("99") # Aceita 0 a 99
        self.num_input.setToolTip("Número esperado de falantes (0 para detecção automática). Usado apenas com AssemblyAI.")
        self.num_input.setMaximumWidth(40) # Largura menor
        self.num_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        num_layout.addWidget(num_label)
        num_layout.addWidget(self.num_input)
        self.speaker_identification_cb = QCheckBox("Speaker Identification (nomes da ata)")
        self.speaker_identification_cb.setToolTip("Identificar falantes pelos nomes da ata (juiz, partes, advogados). Requer arquivo de ata. Ao ativar, o pós-processamento é definido como 'Nenhum'.")
        self.speaker_identification_cb.stateChanged.connect(self._on_speaker_identification_toggled)
        num_layout.addWidget(self.speaker_identification_cb)
        params_group.addWidget(self.num_container) # Adiciona container ao grupo
        params_group.addStretch() # Empurra para a esquerda
        controls_layout.addLayout(params_group)


        # --- 3. Configuração das APIs --- MODIFICADO Título
        keys_group = QWidget()
        keys_layout = QVBoxLayout(keys_group)
        keys_layout.setSpacing(8)
        keys_layout.setContentsMargins(0, 10, 0, 5)
        keys_title = QLabel("<b>3. Configuração das APIs (Chaves/Credenciais):</b>") # Título mais genérico
        keys_layout.addWidget(keys_title)

        # Assembly AI API Key
        self.api_assembly_container = QWidget()
        api_assembly_layout = QHBoxLayout(self.api_assembly_container)
        api_assembly_layout.setContentsMargins(0, 0, 0, 0)
        api_assembly_label = QLabel("AssemblyAI Key:")
        self.api_key_assembly_input = QLineEdit(self.saved_keys.get('assembly_ai', ''))
        self.api_key_assembly_input.setPlaceholderText("Necessária para Transcrição AssemblyAI (pode usar padrão)")
        self.api_key_assembly_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_assembly_layout.addWidget(api_assembly_label)
        api_assembly_layout.addWidget(self.api_key_assembly_input)
        keys_layout.addWidget(self.api_assembly_container)

        # OpenAI API Keys
        self.api_openai_container = QWidget()
        api_openai_layout = QVBoxLayout(self.api_openai_container)
        api_openai_layout.setContentsMargins(0, 0, 0, 0)
        api_openai_transcription_row = QHBoxLayout()
        api_openai_post_row = QHBoxLayout()
        api_openai_transcription_label = QLabel("OpenAI Key (transcrição):")
        self.api_key_openai_transcription_input = QLineEdit(self.saved_keys.get('openai_transcription', self.saved_keys.get('openai', '')))
        self.api_key_openai_transcription_input.setPlaceholderText("Necessária para modelos OpenAI de áudio")
        self.api_key_openai_transcription_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_openai_transcription_row.addWidget(api_openai_transcription_label)
        api_openai_transcription_row.addWidget(self.api_key_openai_transcription_input)
        api_openai_post_label = QLabel("OpenAI Key (pós):")
        self.api_key_openai_post_input = QLineEdit(self.saved_keys.get('openai_post', self.saved_keys.get('openai', '')))
        self.api_key_openai_post_input.setPlaceholderText("Necessária para pós-processamento OpenAI")
        self.api_key_openai_post_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_openai_post_row.addWidget(api_openai_post_label)
        api_openai_post_row.addWidget(self.api_key_openai_post_input)
        self.api_key_openai_input = self.api_key_openai_transcription_input
        api_openai_layout.addLayout(api_openai_transcription_row)
        api_openai_layout.addLayout(api_openai_post_row)
        keys_layout.addWidget(self.api_openai_container)

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

        # Gemini API Keys
        self.api_gemini_container = QWidget()
        api_gemini_layout = QVBoxLayout(self.api_gemini_container)
        api_gemini_layout.setContentsMargins(0, 0, 0, 0)
        api_gemini_transcription_row = QHBoxLayout()
        api_gemini_post_row = QHBoxLayout()
        api_gemini_transcription_label = QLabel("Gemini Key (transcrição):")
        self.api_key_gemini_transcription_input = QLineEdit(self.saved_keys.get('gemini_transcription', self.saved_keys.get('gemini', '')))
        self.api_key_gemini_transcription_input.setPlaceholderText("Necessária para transcrição Gemini")
        self.api_key_gemini_transcription_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_gemini_transcription_row.addWidget(api_gemini_transcription_label)
        api_gemini_transcription_row.addWidget(self.api_key_gemini_transcription_input)
        api_gemini_post_label = QLabel("Gemini Key (pós):")
        self.api_key_gemini_post_input = QLineEdit(self.saved_keys.get('gemini_post', self.saved_keys.get('gemini', '')))
        self.api_key_gemini_post_input.setPlaceholderText("Necessária para pós-processamento Gemini")
        self.api_key_gemini_post_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_gemini_post_row.addWidget(api_gemini_post_label)
        api_gemini_post_row.addWidget(self.api_key_gemini_post_input)
        self.api_key_gemini_input = self.api_key_gemini_transcription_input
        api_gemini_layout.addLayout(api_gemini_transcription_row)
        api_gemini_layout.addLayout(api_gemini_post_row)
        keys_layout.addWidget(self.api_gemini_container)

        # Soniox API Key
        self.api_soniox_container = QWidget()
        api_soniox_layout = QHBoxLayout(self.api_soniox_container)
        api_soniox_layout.setContentsMargins(0, 0, 0, 0)
        api_soniox_label = QLabel("Soniox Key:")
        self.api_key_soniox_input = QLineEdit(self.saved_keys.get('soniox', ''))
        self.api_key_soniox_input.setPlaceholderText("Necessaria para Transcricao Soniox")
        self.api_key_soniox_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_soniox_layout.addWidget(api_soniox_label)
        api_soniox_layout.addWidget(self.api_key_soniox_input)
        keys_layout.addWidget(self.api_soniox_container)

        # OpenRouter API Key
        self.api_openrouter_container = QWidget()
        api_openrouter_layout = QHBoxLayout(self.api_openrouter_container)
        api_openrouter_layout.setContentsMargins(0, 0, 0, 0)
        api_openrouter_label = QLabel("OpenRouter Key:")
        self.api_key_openrouter_input = QLineEdit(self.saved_keys.get('openrouter', ''))
        self.api_key_openrouter_input.setPlaceholderText("Necessária para transcrição e pós-processamento via OpenRouter")
        self.api_key_openrouter_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_openrouter_layout.addWidget(api_openrouter_label)
        api_openrouter_layout.addWidget(self.api_key_openrouter_input)
        keys_layout.addWidget(self.api_openrouter_container)

        controls_layout.addWidget(keys_group)

        # --- 4. Pós-processamento ---
        # (Layout mantido como antes)
        post_process_group = QWidget()
        post_process_layout = QHBoxLayout(post_process_group)
        post_process_layout.setContentsMargins(0, 5, 0, 5)
        post_process_label = QLabel("<b>4. Pós-processamento (Identificar Interlocutores):</b>") # Numerado
        self.use_claude_radio = QRadioButton("Anthropic")
        self.use_openai_radio = QRadioButton("Open AI")
        self.use_gemini_radio = QRadioButton("Google")
        self.use_openrouter_radio = QRadioButton("OpenRouter")
        self.use_none_radio = QRadioButton("Nenhum (Apenas Transcrever)")
        self.use_claude_radio.setChecked(True) # Padrão
        post_process_layout.addWidget(post_process_label)
        post_process_layout.addWidget(self.use_claude_radio)
        post_process_layout.addWidget(self.use_openai_radio)
        post_process_layout.addWidget(self.use_gemini_radio)
        post_process_layout.addWidget(self.use_openrouter_radio)
        post_process_layout.addWidget(self.use_none_radio)
        post_process_layout.addStretch()
        controls_layout.addWidget(post_process_group)

        post_model_group = QHBoxLayout()
        post_model_group.setContentsMargins(0, 0, 0, 0)
        post_model_label = QLabel("Modelo de pós-processamento:")
        self.post_model_combo = QComboBox()
        self.post_model_combo.setToolTip("Modelo de texto usado para identificar interlocutores e aplicar as informações da ata.")
        post_model_group.addWidget(post_model_label)
        post_model_group.addWidget(self.post_model_combo)
        post_model_group.addStretch()
        controls_layout.addLayout(post_model_group)

        # --- 5. Documento Word (.docx) ---
        word_group = QWidget()
        word_layout = QVBoxLayout(word_group)
        word_layout.setContentsMargins(0, 5, 0, 5)
        word_layout.setSpacing(2)
        word_title = QLabel("<b>5. Documento Word (.docx):</b>")
        word_layout.addWidget(word_title)
        self.generate_docx_checkbox = QCheckBox("Gerar DOCX com transcrição organizada por títulos")
        self.generate_docx_checkbox.setToolTip("Gera o DOCX usando o TXT final e a ata da seção 2. O arquivo será salvo na pasta do TXT.")
        self.generate_docx_checkbox.setEnabled(DOCX_GENERATOR_AVAILABLE)
        if not DOCX_GENERATOR_AVAILABLE:
            self.generate_docx_checkbox.setToolTip("Módulo de geração DOCX indisponível. Verifique o arquivo KiwiscribeWord.py e dependências docx.")
        word_layout.addWidget(self.generate_docx_checkbox)
        controls_layout.addWidget(word_group)

        # Adicionar widget de controles ao layout principal
        main_layout.addWidget(controls_widget)

        # --- Botões de Ação ---
        # (Layout mantido como antes)
        buttons_group = QHBoxLayout()
        buttons_group.addStretch() # Empurra para a direita
        self.transcribe_btn = QPushButton("🚀 Iniciar Processo")
        self.transcribe_btn.setStyleSheet("padding: 8px 15px; font-weight: bold; background-color: #4CAF50; color: white; border: none; border-radius: 4px;")
        self.transcribe_btn.setToolTip("Inicia a transcrição e o pós-processamento selecionados")
        self.transcribe_btn.clicked.connect(self.start_transcription)
        close_btn = QPushButton("Encerrar")
        close_btn.setStyleSheet("padding: 8px 15px; background-color: #f44336; color: white; border: none; border-radius: 4px;")
        close_btn.clicked.connect(self.close_app)
        buttons_group.addWidget(self.transcribe_btn)
        buttons_group.addWidget(close_btn)
        main_layout.addLayout(buttons_group)

        # --- Área de Mensagens ---
        # (Layout mantido como antes)
        message_label = QLabel("<b>Log de Mensagens:</b>")
        main_layout.addWidget(message_label)
        self.message_box = QTextEdit()
        self.message_box.setReadOnly(True)
        self.message_box.setMinimumHeight(150)
        self.message_box.ensureCursorVisible()
        self.message_box.setStyleSheet("background-color: #f8f8f8; border: 1px solid #d0d0d0; font-family: Consolas, monospace; font-size: 10pt;")
        main_layout.addWidget(self.message_box)

        # Configurações adicionais
        self.transcription_thread = None
        self.running = False
        self.current_log_file = None
        self.current_run_suffix = ""
        self.model_cache = {}
        self._last_transcription_provider = None
        self._last_post_provider = None

        # --- Conectar sinais aos slots --- MODIFICADO
        self.service_assembly.toggled.connect(self._on_transcription_provider_toggled)
        self.service_openai.toggled.connect(self._on_transcription_provider_toggled)
        self.service_gemini.toggled.connect(self._on_transcription_provider_toggled)
        self.service_openrouter.toggled.connect(self._on_transcription_provider_toggled)
        self.service_soniox.toggled.connect(self._on_transcription_provider_toggled)
        self.service_just_post_process.toggled.connect(self._on_transcription_provider_toggled)
        self.service_just_docx.toggled.connect(self._on_transcription_provider_toggled)
        self.use_claude_radio.toggled.connect(self._on_post_provider_toggled)
        self.use_openai_radio.toggled.connect(self._on_post_provider_toggled)
        self.use_gemini_radio.toggled.connect(self._on_post_provider_toggled)
        self.use_openrouter_radio.toggled.connect(self._on_post_provider_toggled)
        self.use_none_radio.toggled.connect(self._on_post_provider_toggled)
        self.transcription_model_combo.currentIndexChanged.connect(self.update_ui_visibility)
        self.post_model_combo.currentIndexChanged.connect(self.update_ui_visibility)
        self.api_key_openai_transcription_input.editingFinished.connect(
            lambda: self._refresh_model_combos(fetch_remote=True, target='transcription') if self.service_openai.isChecked() else None
        )
        self.api_key_openai_post_input.editingFinished.connect(
            lambda: self._refresh_model_combos(fetch_remote=True, target='post') if self.use_openai_radio.isChecked() else None
        )
        self.api_key_claude_input.editingFinished.connect(
            lambda: self._refresh_model_combos(fetch_remote=True, target='post') if self.use_claude_radio.isChecked() else None
        )
        self.api_key_gemini_transcription_input.editingFinished.connect(
            lambda: self._refresh_model_combos(fetch_remote=True, target='transcription') if self.service_gemini.isChecked() else None
        )
        self.api_key_gemini_post_input.editingFinished.connect(
            lambda: self._refresh_model_combos(fetch_remote=True, target='post') if self.use_gemini_radio.isChecked() else None
        )
        self.api_key_openrouter_input.editingFinished.connect(
            lambda: self._refresh_model_combos(fetch_remote=True)
            if (self.service_openrouter.isChecked() or self.use_openrouter_radio.isChecked())
            else None
        )

        self.update_ui_visibility() # Inicializar visibilidade
        # Carregar configurações salvas (última sessão)
        self.load_settings()
        # Atualiza modelos automaticamente no início para os provedores selecionados.
        self._refresh_model_combos(fetch_remote=True)
        self._last_transcription_provider = self._current_transcription_service()
        self._last_post_provider = self._current_post_provider()

    def _on_speaker_identification_toggled(self, state):
        """Ao marcar Speaker Identification, seleciona automaticamente 'Nenhum (Apenas Transcrever)' no pós-processamento."""
        if self.speaker_identification_cb.isChecked():
            self.use_none_radio.setChecked(True)
        self.update_ui_visibility()

    def _sanitize_model_tag(self, value):
        """Normaliza texto para uso seguro em sufixos de arquivo."""
        normalized = re.sub(r'[^a-z0-9]+', '_', (value or '').lower()).strip('_')
        return normalized if normalized else "na"

    def _current_transcription_service(self):
        if self.service_assembly.isChecked():
            return "AssemblyAI"
        if self.service_openai.isChecked():
            return "gpt-4o-transcribe"
        if self.service_gemini.isChecked():
            return "Gemini"
        if self.service_openrouter.isChecked():
            return "OpenRouter"
        if self.service_soniox.isChecked():
            return "Soniox"
        if self.service_just_post_process.isChecked():
            return "JustPostProcess"
        if self.service_just_docx.isChecked():
            return "JustGenerateDocx"
        return "AssemblyAI"

    def _current_post_provider(self):
        if self.use_claude_radio.isChecked():
            return "Claude"
        if self.use_openai_radio.isChecked():
            return "OpenAI"
        if self.use_gemini_radio.isChecked():
            return "Gemini"
        if self.use_openrouter_radio.isChecked():
            return "OpenRouter"
        return "None"

    def _populate_combo(self, combo, options, preferred_value=None):
        current_value = preferred_value or combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for label, value in options:
            combo.addItem(label, value)
        index = combo.findData(current_value)
        if index < 0:
            index = 0
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _get_provider_key(self, provider, purpose):
        if provider == "gpt-4o-transcribe":
            return self.api_key_openai_transcription_input.text().strip() if purpose == 'transcription' else self.api_key_openai_post_input.text().strip()
        if provider == "OpenAI":
            return self.api_key_openai_post_input.text().strip()
        if provider == "OpenRouter":
            return self.api_key_openrouter_input.text().strip()
        if provider == "Gemini":
            return self.api_key_gemini_transcription_input.text().strip() if purpose == 'transcription' else self.api_key_gemini_post_input.text().strip()
        if provider == "Claude":
            return self.api_key_claude_input.text().strip()
        if provider == "AssemblyAI":
            return self.api_key_assembly_input.text().strip()
        if provider == "Soniox":
            return self.api_key_soniox_input.text().strip()
        return ""

    def _fallback_models(self, provider, purpose):
        if purpose == 'transcription':
            return TRANSCRIPTION_MODELS.get(provider, TRANSCRIPTION_MODELS["AssemblyAI"])
        return POST_PROCESSING_MODELS.get(provider, POST_PROCESSING_MODELS["None"])

    def _fetch_openai_models(self, api_key, purpose):
        response = requests.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        response.raise_for_status()
        ids = sorted(item.get('id', '') for item in response.json().get('data', []) if item.get('id'))
        if purpose == 'transcription':
            filtered = [m for m in ids if 'transcribe' in m or m == 'whisper-1']
        else:
            excluded = ('transcribe', 'whisper', 'tts', 'embedding', 'moderation', 'realtime', 'audio')
            filtered = [m for m in ids if (m.startswith(('gpt-', 'o', 'chatgpt-')) and not any(x in m for x in excluded))]
        return [(m, m) for m in filtered]

    def _fetch_anthropic_models(self, api_key):
        response = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=15,
        )
        response.raise_for_status()
        ids = sorted(item.get('id', '') for item in response.json().get('data', []) if item.get('id'))
        return [(m, m) for m in ids]

    def _fetch_google_models(self, api_key, purpose):
        response = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            timeout=15,
        )
        response.raise_for_status()
        models = []
        for item in response.json().get('models', []):
            name = (item.get('name') or '').replace('models/', '')
            methods = item.get('supportedGenerationMethods') or []
            if not name or 'generateContent' not in methods:
                continue
            if any(skip in name for skip in ('embedding', 'aqa', 'tts')):
                continue
            # Google does not expose an "audio input" flag in this listing; Gemini generateContent models are candidates.
            models.append(name)
        return [(m, m) for m in sorted(set(models))]

    def _openrouter_modalities_from_model(self, model):
        architecture = model.get('architecture') or {}
        inputs = architecture.get('input_modalities') or []
        outputs = architecture.get('output_modalities') or []
        input_modalities = [str(m).strip().lower() for m in inputs if isinstance(m, str)]
        output_modalities = [str(m).strip().lower() for m in outputs if isinstance(m, str)]
        return input_modalities, output_modalities

    def _openrouter_fallback_accept(self, model_id, purpose):
        model_id = (model_id or "").lower()
        if not model_id:
            return False
        if purpose == 'transcription':
            # Transcrição via /chat/completions: modelos STT dedicados OU LLMs com áudio.
            return any(token in model_id for token in ('whisper', 'transcribe', 'stt', 'audio', 'gemini', 'gpt-4o'))
        excluded = ('transcribe', 'whisper', 'tts', 'embedding', 'moderation')
        if any(token in model_id for token in excluded):
            return False
        return any(token in model_id for token in ('gpt', 'claude', 'gemini', 'llama', 'qwen', 'mistral', 'deepseek', 'o1', 'o3', 'o4'))

    def _fetch_openrouter_models(self, api_key, purpose):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://kiwiscribe.local",
            "X-Title": "Kiwiscribe",
        }
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json() or {}
        data = payload.get('data') or []

        options = []
        for item in data:
            model_id = item.get('id')
            if not model_id:
                continue

            input_modalities, output_modalities = self._openrouter_modalities_from_model(item)
            supports = False
            if input_modalities and output_modalities:
                if purpose == 'transcription':
                    # A transcrição usa /chat/completions com input_audio, então qualquer
                    # modelo que aceite áudio na entrada e gere texto serve.
                    supports = ('audio' in input_modalities) and ('text' in output_modalities)
                else:
                    supports = ('text' in input_modalities) and ('text' in output_modalities)
            else:
                supports = self._openrouter_fallback_accept(model_id, purpose)

            if not supports:
                continue

            display_name = item.get('name') or model_id
            options.append((display_name, model_id))

        deduped = {}
        for label, value in options:
            if value not in deduped:
                deduped[value] = label

        normalized = sorted([(label, value) for value, label in deduped.items()], key=lambda x: x[0].lower())
        max_items = 250
        if len(normalized) > max_items:
            self.update_message_box(f"ℹ️ OpenRouter: lista filtrada contém {len(normalized)} modelos. Mostrando os {max_items} primeiros para manter a UI responsiva.")
            normalized = normalized[:max_items]
        return normalized

    def _build_model_refresh_error_message(self, provider, error):
        if isinstance(error, requests.exceptions.ConnectionError):
            return (
                f"❌ Sem conexão com a internet: não foi possível consultar modelos em tempo real de {provider}. "
                "Verifique sua conexão e tente novamente."
            )
        if isinstance(error, requests.exceptions.Timeout):
            return (
                f"❌ Tempo de conexão esgotado ao consultar modelos de {provider}. "
                "Verifique sua internet e tente novamente."
            )
        return f"⚠️ Falha ao atualizar modelos de {provider}: {error}."

    def _get_models_for_provider(self, provider, purpose, fetch_remote=False):
        cache_key = (provider, purpose)
        fallback = self._fallback_models(provider, purpose)
        if not fetch_remote and cache_key in self.model_cache:
            return self.model_cache[cache_key]
        if not fetch_remote:
            return fallback
        api_key = self._get_provider_key(provider, purpose)
        if provider in ("AssemblyAI", "Soniox", "JustPostProcess", "JustGenerateDocx", "None"):
            self.update_message_box(f"ℹ️ {provider}: usando lista local de modelos/serviços disponíveis.")
            return fallback
        if not api_key:
            self.update_message_box(f"⚠️ Informe a API Key de {provider} para atualizar modelos em tempo real. Usando lista local.")
            return fallback
        try:
            if provider in ("gpt-4o-transcribe", "OpenAI"):
                models = self._fetch_openai_models(api_key, purpose)
            elif provider == "Claude":
                models = self._fetch_anthropic_models(api_key)
            elif provider == "Gemini":
                models = self._fetch_google_models(api_key, purpose)
            elif provider == "OpenRouter":
                models = self._fetch_openrouter_models(api_key, purpose)
            else:
                models = fallback
            if not models:
                self.update_message_box(f"⚠️ {provider}: nenhum modelo compatível retornado pela API. Usando lista local.")
                return fallback
            self.model_cache[cache_key] = models
            self.update_message_box(f"✅ {provider}: {len(models)} modelo(s) carregado(s) em tempo real.")
            return models
        except Exception as e:
            self.update_message_box(f"{self._build_model_refresh_error_message(provider, e)} Usando lista local.")
            return fallback

    def _refresh_model_combos(self, fetch_remote=False, target=None):
        transcription_provider = self._current_transcription_service()
        post_provider = self._current_post_provider()
        if target in (None, 'transcription'):
            self._populate_combo(
                self.transcription_model_combo,
                self._get_models_for_provider(transcription_provider, 'transcription', fetch_remote=fetch_remote),
            )
        if target in (None, 'post'):
            self._populate_combo(
                self.post_model_combo,
                self._get_models_for_provider(post_provider, 'post', fetch_remote=fetch_remote),
            )

    def _on_transcription_provider_toggled(self, checked):
        if not checked:
            return
        self.update_ui_visibility()
        current_provider = self._current_transcription_service()
        if current_provider != self._last_transcription_provider:
            self._refresh_model_combos(fetch_remote=True, target='transcription')
            self._last_transcription_provider = current_provider

    def _on_post_provider_toggled(self, checked):
        if not checked:
            return
        self.update_ui_visibility()
        current_provider = self._current_post_provider()
        if current_provider != self._last_post_provider:
            self._refresh_model_combos(fetch_remote=True, target='post')
            self._last_post_provider = current_provider

    def _selected_transcription_model(self):
        return self.transcription_model_combo.currentData() or self._get_transcription_model_tag(self._current_transcription_service())

    def _selected_post_model(self):
        return self.post_model_combo.currentData() or "none"

    def _get_transcription_model_tag(self, selected_service):
        """Retorna tag padronizada do modelo de transcrição para nomes de arquivo."""
        if hasattr(self, 'transcription_model_combo'):
            selected = self._selected_transcription_model()
            if selected:
                return self._sanitize_model_tag(selected)
        default_value = TRANSCRIPTION_MODELS.get(selected_service, [(selected_service, selected_service)])[0][1]
        return self._sanitize_model_tag(default_value)

    def _get_post_model_tag(self):
        """Retorna tag padronizada do modelo de pós-processamento para nomes de arquivo."""
        if hasattr(self, 'post_model_combo'):
            return self._sanitize_model_tag(self._selected_post_model())
        return "none"

    def _build_models_suffix(self, selected_service):
        """Monta sufixo com modelos de transcrição e pós-processamento."""
        tts_tag = self._get_transcription_model_tag(selected_service)
        post_tag = self._get_post_model_tag()
        return f"_tts_{tts_tag}_post_{post_tag}"

    def _apply_suffix_to_output_path(self, file_path, suffix):
        """Garante que o arquivo final contenha o sufixo de modelos."""
        if not file_path or not suffix:
            return file_path
        base, ext = os.path.splitext(file_path)
        if base.endswith(suffix):
            return file_path
        new_path = f"{base}{suffix}{ext}"
        if not os.path.exists(file_path):
            return file_path
        try:
            os.replace(file_path, new_path)
            return new_path
        except Exception as e:
            self.worker_signals.message.emit(f"⚠️ Aviso: Não foi possível aplicar sufixo ao arquivo final: {e}")
            return file_path

    def save_settings(self):
        """Salva as configurações atuais da interface em um arquivo JSON."""
        settings = {
            'service_assembly': self.service_assembly.isChecked(),
            'service_openai': self.service_openai.isChecked(),
            'service_gemini': self.service_gemini.isChecked(),
            'service_openrouter': self.service_openrouter.isChecked(),
            'service_soniox': self.service_soniox.isChecked(),
            'service_just_post_process': self.service_just_post_process.isChecked(),
            'service_just_docx': self.service_just_docx.isChecked(),
            
            'use_claude': self.use_claude_radio.isChecked(),
            'use_openai': self.use_openai_radio.isChecked(),
            'use_gemini': self.use_gemini_radio.isChecked(),
            'use_openrouter': self.use_openrouter_radio.isChecked(),
            'use_none': self.use_none_radio.isChecked(),
            'transcription_model': self._selected_transcription_model(),
            'post_model': self._selected_post_model(),
            'generate_docx': self.generate_docx_checkbox.isChecked(),
            
            'num_interlocutors': self.num_input.text(),
            'speaker_identification': self.speaker_identification_cb.isChecked()
        }
        try:
            settings_path = os.path.join(os.path.expanduser('~'), '.kiwiscribe_settings.json')
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            # print(f"Configurações salvas: {settings_path}")
        except Exception as e:
            print(f"Erro ao salvar configurações: {e}")

    def load_settings(self):
        """Carrega e aplica as configurações da última sessão."""
        settings_path = os.path.join(os.path.expanduser('~'), '.kiwiscribe_settings.json')
        if not os.path.exists(settings_path):
            return

        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            # Restaura Serviço de Transcrição
            if settings.get('service_assembly', True): self.service_assembly.setChecked(True)
            elif settings.get('service_openai', False): self.service_openai.setChecked(True)
            elif settings.get('service_gemini', False): self.service_gemini.setChecked(True)
            elif settings.get('service_openrouter', False): self.service_openrouter.setChecked(True)
            elif settings.get('service_soniox', False): self.service_soniox.setChecked(True)
            elif settings.get('service_just_post_process', False): self.service_just_post_process.setChecked(True)
            elif settings.get('service_just_docx', False): self.service_just_docx.setChecked(True)

            # Restaura Pós-processamento
            if settings.get('use_claude', True): self.use_claude_radio.setChecked(True)
            elif settings.get('use_openai', False): self.use_openai_radio.setChecked(True)
            elif settings.get('use_gemini', False): self.use_gemini_radio.setChecked(True)
            elif settings.get('use_openrouter', False): self.use_openrouter_radio.setChecked(True)
            elif settings.get('use_none', False): self.use_none_radio.setChecked(True)

            # Restaura Nº Interlocutores
            if 'num_interlocutors' in settings:
                self.num_input.setText(settings['num_interlocutors'])

            self._refresh_model_combos()
            if settings.get('transcription_model'):
                index = self.transcription_model_combo.findData(settings['transcription_model'])
                if index >= 0:
                    self.transcription_model_combo.setCurrentIndex(index)
            if settings.get('post_model'):
                index = self.post_model_combo.findData(settings['post_model'])
                if index >= 0:
                    self.post_model_combo.setCurrentIndex(index)

            self.generate_docx_checkbox.setChecked(settings.get('generate_docx', False))

            # Atualiza visibilidade após restaurar
            self.update_ui_visibility()
            
        except Exception as e:
            print(f"Erro ao carregar configurações: {e}")


    def update_ui_visibility(self):
        """Atualiza a visibilidade e estado dos campos da UI."""
        self.setUpdatesEnabled(False)
        try:
        # Verifica estados dos RadioButtons
            is_assembly_service = self.service_assembly.isChecked()
            is_openai_service = self.service_openai.isChecked()
            is_gemini_service = self.service_gemini.isChecked()
            is_openrouter_service = self.service_openrouter.isChecked()
            is_just_post_process = self.service_just_post_process.isChecked()
            is_just_docx = self.service_just_docx.isChecked()
            is_soniox_service = self.service_soniox.isChecked()

            is_claude_post = self.use_claude_radio.isChecked()
            is_openai_post = self.use_openai_radio.isChecked()
            is_gemini_post = self.use_gemini_radio.isChecked()
            is_openrouter_post = self.use_openrouter_radio.isChecked()
            is_no_post = self.use_none_radio.isChecked()

        # Visibilidade Nº Interlocutores (só AssemblyAI)
            self.num_container.setVisible(is_assembly_service)

        # Visibilidade dos campos de arquivo
        # Se for "Apenas Pós-processar", esconde Áudio e mostra Transcrição.
        # Caso contrário, mostra Áudio e esconde Transcrição.
            self.audio_group_container.setVisible(not (is_just_post_process or is_just_docx))
            self.transcription_group_container.setVisible(is_just_post_process or is_just_docx)

        # Visibilidade dos campos/containers de API/Credenciais
            api_visible = not is_just_docx
            self.api_assembly_container.setVisible(api_visible and is_assembly_service)
            self.api_openai_container.setVisible(api_visible and (is_openai_service or is_openai_post))
            self.api_claude_container.setVisible(api_visible and is_claude_post)
            self.api_gemini_container.setVisible(api_visible and (is_gemini_service or is_gemini_post))
            self.api_soniox_container.setVisible(api_visible and is_soniox_service)
            self.api_openrouter_container.setVisible(api_visible and (is_openrouter_service or is_openrouter_post))
        # Removida a linha que referenciada google_credentials_label

        # Atualiza o texto do botão principal e tooltip
            service_name = ""
            if is_assembly_service: service_name = "AssemblyAI"
            elif is_openai_service: service_name = "OpenAI-GPT"
            elif is_gemini_service: service_name = "Gemini"
            elif is_openrouter_service: service_name = "OpenRouter"
            elif is_soniox_service: service_name = "Soniox"
            elif is_just_post_process: service_name = "Pós-processar Arquivo"
            elif is_just_docx: service_name = "Gerar DOCX"

            self.transcription_model_combo.setEnabled(not (is_just_post_process or is_just_docx))
            self.use_claude_radio.setEnabled(not is_just_docx)
            self.use_openai_radio.setEnabled(not is_just_docx)
            self.use_gemini_radio.setEnabled(not is_just_docx)
            self.use_openrouter_radio.setEnabled(not is_just_docx)
            self.use_none_radio.setEnabled(not is_just_docx)
            self.post_model_combo.setEnabled((not is_no_post) and (not is_just_docx))

            if is_just_docx:
                if not self.use_none_radio.isChecked():
                    self.use_none_radio.blockSignals(True)
                    self.use_none_radio.setChecked(True)
                    self.use_none_radio.blockSignals(False)
                if not self.generate_docx_checkbox.isChecked():
                    self.generate_docx_checkbox.blockSignals(True)
                    self.generate_docx_checkbox.setChecked(True)
                    self.generate_docx_checkbox.blockSignals(False)
                self.post_model_combo.setEnabled(False)
                self.generate_docx_checkbox.setEnabled(False)
            else:
                self.generate_docx_checkbox.setEnabled(DOCX_GENERATOR_AVAILABLE)

            if is_just_docx:
                self.transcribe_btn.setText("📝 Gerar DOCX")
                self.transcribe_btn.setToolTip("Gera DOCX a partir do TXT selecionado e ata opcional.")
            elif is_just_post_process:
                self.transcribe_btn.setText("🚀 Iniciar Pós-processamento")
                self.transcribe_btn.setToolTip("Inicia o pós-processamento do arquivo de texto selecionado.")
            elif is_no_post:
                self.transcribe_btn.setText(f"🏁 Iniciar Transcrição ({service_name})")
                self.transcribe_btn.setToolTip(f"Inicia apenas a transcrição do áudio com {service_name}.")
            else:
                post_processor_name = ""
                if is_claude_post: post_processor_name = "Claude"
                elif is_openai_post: post_processor_name = "OpenAI"
                elif is_gemini_post: post_processor_name = "Gemini"
                elif is_openrouter_post: post_processor_name = "OpenRouter"
                self.transcribe_btn.setText(f"🚀 Iniciar ({service_name} + {post_processor_name})")
                self.transcribe_btn.setToolTip(f"Inicia a transcrição ({service_name}) e depois pós-processamento ({post_processor_name}).")
        finally:
            self.setUpdatesEnabled(True)

    # --- Funções browse_file_dialog, browse_file_fallback ---
    # (Mantidas como na versão anterior)
    def browse_file_dialog(self, file_type):
        """Abre o diálogo personalizado para selecionar arquivos de áudio ou ata."""
        download_dir = get_download_dir()
        if file_type == 'audio':
            input_field = self.audio_input
        elif file_type == 'transcription':
            input_field = self.transcription_input
        else: # ata
            input_field = self.ata_input

        current_path = input_field.text()
        if not current_path or not os.path.isdir(os.path.dirname(current_path)):
             start_dir = download_dir
        else:
             start_dir = os.path.dirname(current_path) # Começa no dir do arquivo atual

        try:
            all_files = [f for f in os.listdir(download_dir) if os.path.isfile(os.path.join(download_dir, f))]
        except FileNotFoundError:
            self.update_message_box(f"Erro: Diretório de downloads '{download_dir}' não encontrado.")
            all_files = []
        except Exception as e:
             self.update_message_box(f"Erro ao listar arquivos em '{download_dir}': {e}")
             all_files = []


        if file_type == 'audio':
            # Filtra por extensões comuns de áudio (case-insensitive)
            audio_extensions = ('.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.opus', '.amr', '.wma')
            relevant_files = [f for f in all_files if f.lower().endswith(audio_extensions)]
            title_suffix = "de Áudio"
        elif file_type == 'transcription':
            # Filtra por extensões de texto
            txt_extensions = ('.txt',)
            relevant_files = [f for f in all_files if f.lower().endswith(txt_extensions)]
            title_suffix = "de Transcrição"
        elif file_type == 'ata':
            # Filtra por extensões de ata
            ata_extensions = ('.pdf', '.txt')
            relevant_files = [f for f in all_files if f.lower().endswith(ata_extensions)]
            title_suffix = "da Ata"
        else:
            return

        if not relevant_files:
            self.update_message_box(f"Nenhum arquivo {title_suffix.lower()} encontrado no diretório de downloads padrão ({download_dir}). Usando diálogo padrão.")
            # Tenta o QFileDialog padrão como fallback
            self.browse_file_fallback(file_type)
            return

        dialog = FileTableDialog(relevant_files, file_type, self)
        if dialog.exec(): # Mostra o diálogo e espera (bloqueia)
            selected_file = dialog.get_selected_file()
            if selected_file:
                full_path = os.path.join(download_dir, selected_file)
                input_field.setText(full_path)
                self.update_message_box(f"Arquivo {title_suffix.lower()} selecionado: {full_path}")
        else:
            # O usuário cancelou
            self.update_message_box(f"Seleção de arquivo {title_suffix.lower()} cancelada.")


    def browse_file_fallback(self, file_type):
        """Fallback para o QFileDialog padrão se o diálogo personalizado falhar."""
        self.update_message_box("Usando diálogo de arquivo padrão...")
        title = "Selecionar Arquivo"
        if file_type == 'audio':
             filters = "Arquivos de Áudio (*.mp3 *.wav *.m4a *.ogg *.flac *.aac *.opus *.amr *.wma);;Todos os Arquivos (*)"
             title = "Selecionar Arquivo de Áudio"
             input_field = self.audio_input
        elif file_type == 'transcription':
             filters = "Arquivos de Texto (*.txt);;Todos os Arquivos (*)"
             title = "Selecionar Arquivo de Transcrição"
             input_field = self.transcription_input
        else:
             filters = "Documentos Suportados (*.pdf *.txt);;Todos os Arquivos (*)"
             title = "Selecionar Arquivo da Ata"
             input_field = self.ata_input
        
        start_dir = get_download_dir()

        file_path, _ = QFileDialog.getOpenFileName(self, title, start_dir, filters)

        if file_path:
            input_field.setText(file_path)
            self.update_message_box(f"Arquivo selecionado (fallback): {file_path}")

    def start_transcription(self):
        """Valida entradas e inicia a transcrição/pós-processamento."""
        if self.running:
            self.update_message_box("Aguarde, um processo já está em execução.")
            return

        # --- Validações --- MODIFICADO
        audio_path = self.audio_input.text().strip()
        ata_path = self.ata_input.text().strip()
        assembly_key = self.api_key_assembly_input.text().strip()
        openai_transcription_key = self.api_key_openai_transcription_input.text().strip()
        openai_post_key = self.api_key_openai_post_input.text().strip()
        claude_key = self.api_key_claude_input.text().strip()
        gemini_transcription_key = self.api_key_gemini_transcription_input.text().strip()
        gemini_post_key = self.api_key_gemini_post_input.text().strip()
        soniox_key = self.api_key_soniox_input.text().strip()
        openrouter_key = self.api_key_openrouter_input.text().strip()

        # Validação Áudio OU Transcrição
        if self.service_just_post_process.isChecked() or self.service_just_docx.isChecked():
            # Validação para modo "Apenas Pós-processar"
             transcription_file = self.transcription_input.text().strip()
             if not transcription_file:
                  self.update_message_box("❌ Erro: Selecione um arquivo de texto com a transcrição.")
                  return
             if not os.path.exists(transcription_file):
                  self.update_message_box(f"❌ Erro: Arquivo de transcrição não encontrado em '{transcription_file}'.")
                  return
             # Para esse modo, usamos o arquivo de transcrição como 'audio_path' para passar pro workflow (gambiarra consciente)
             # O workflow vai tratar diferente baseada em flag ou apenas pular transcrição
             audio_path = transcription_file 
        else:
            # Validação Padrão (Áudio)
            if not audio_path:
                 self.update_message_box("❌ Erro: Selecione um arquivo de áudio ou forneça um URL.")
                 return
            is_url = audio_path.startswith('http://') or audio_path.startswith('https://')
            if not is_url:
                # Remove aspas e verifica existência
                if (audio_path.startswith("'") and audio_path.endswith("'")) or \
                   (audio_path.startswith('"') and audio_path.endswith('"')):
                     audio_path = audio_path[1:-1]
                     self.audio_input.setText(audio_path)
                if not os.path.exists(audio_path):
                     self.update_message_box(f"❌ Erro: Arquivo de áudio não encontrado em '{audio_path}'.")
                     return

        # Validação Ata
        if ata_path:
            if (ata_path.startswith("'") and ata_path.endswith("'")) or \
               (ata_path.startswith('"') and ata_path.endswith('"')):
                 ata_path = ata_path[1:-1]
                 self.ata_input.setText(ata_path)
            if not os.path.exists(ata_path):
                 self.update_message_box(f"⚠️ Aviso: Arquivo da ata '{ata_path}' não encontrado. Continuando sem ele.")
                 ata_path = ""
                 self.ata_input.setText("")
        else:
             self.update_message_box("ℹ️ Info: Arquivo da ata não fornecido.")

        # Valida chaves/credenciais necessárias
        is_docx_only = self.service_just_docx.isChecked()
        if self.service_gemini.isChecked() and not gemini_transcription_key:
            self.update_message_box("❌ Erro: API Key do Gemini é necessária para Transcrição Gemini.")
            return
        if (not is_docx_only) and self.use_gemini_radio.isChecked() and not gemini_post_key:
            self.update_message_box("❌ Erro: API Key do Gemini é necessária para Pós-processamento Gemini.")
            return

        if self.service_assembly.isChecked() and not assembly_key and not self.saved_keys.get('assembly_ai',''):
             self.update_message_box("⚠️ Aviso: Nenhuma API Key da AssemblyAI fornecida ou salva. Tentará usar uma chave padrão interna.")
        if self.service_openai.isChecked() and not openai_transcription_key:
            self.update_message_box("❌ Erro: API Key do OpenAI é necessária para Transcrição GPT.")
            return
        if self.service_soniox.isChecked() and not soniox_key:
            self.update_message_box("❌ Erro: API Key do Soniox é necessária para Transcrição Soniox.")
            return
        if self.service_openrouter.isChecked() and not openrouter_key:
            self.update_message_box("❌ Erro: API Key do OpenRouter é necessária para Transcrição OpenRouter.")
            return
        if (not is_docx_only) and self.use_openai_radio.isChecked() and not openai_post_key:
            self.update_message_box("❌ Erro: API Key do OpenAI é necessária para Pós-processamento GPT.")
            return
        if (not is_docx_only) and self.use_claude_radio.isChecked() and not claude_key:
             self.update_message_box("❌ Erro: API Key do Claude é necessária para Pós-processamento Claude.")
             return
        if (not is_docx_only) and self.use_openrouter_radio.isChecked() and not openrouter_key:
             self.update_message_box("❌ Erro: API Key do OpenRouter é necessária para Pós-processamento OpenRouter.")
             return

        if is_docx_only and not DOCX_GENERATOR_AVAILABLE:
            self.update_message_box("❌ Erro: Gerador DOCX indisponível. Verifique KiwiscribeWord.py e dependências.")
            return

        # Salva chaves inseridas
        save_api_keys(assembly_key if assembly_key else self.saved_keys.get('assembly_ai',''),
                      claude_key,
                      openai_post_key or openai_transcription_key,
                      gemini_post_key or gemini_transcription_key,
                      soniox_key,
                      openai_transcription_key,
                      openai_post_key,
                      gemini_transcription_key,
                      gemini_post_key,
                      openrouter_key)
        self.saved_keys = load_api_keys()

        # Salva Preferências da Sessão (Service, Post-processor, etc)
        self.save_settings()

        # --- Inicia a Thread ---
        self.running = True
        self.transcribe_btn.setEnabled(False)
        self.transcribe_btn.setText("Processando...")

        # Determine Selected Service for Thread
        selected_service = self._current_transcription_service()
        transcription_model = self._selected_transcription_model()
        post_model = self._selected_post_model()
        generate_docx = self.generate_docx_checkbox.isChecked() or (selected_service == "JustGenerateDocx")

        # Snapshot da escolha de pós-processamento no thread da GUI (evita leitura
        # de widgets a partir do thread de trabalho, que pode retornar estado obsoleto
        # e fazer o pós-processamento ser pulado em re-execuções).
        post_processor = None
        if selected_service != "JustGenerateDocx":
            if self.use_claude_radio.isChecked(): post_processor = "Claude"
            elif self.use_openai_radio.isChecked(): post_processor = "OpenAI"
            elif self.use_gemini_radio.isChecked(): post_processor = "Gemini"
            elif self.use_openrouter_radio.isChecked(): post_processor = "OpenRouter"

        self.current_run_suffix = self._build_models_suffix(selected_service)
        log_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.current_log_file = os.path.join(
            get_log_dir(),
            f"kiwiscribe_log_{log_timestamp}{self.current_run_suffix}.txt"
        )

        self.message_box.clear()
        self.update_message_box(f"▶️ Iniciando processo às {datetime.now().strftime('%H:%M:%S')}...")
        self.update_message_box(f"ℹ️ Versão do Kiwiscribe: {APP_VERSION}")

        use_speaker_identification = self.service_assembly.isChecked() and self.speaker_identification_cb.isChecked()
        self.transcription_thread = threading.Thread(
            target=self.perform_transcription_workflow,
            args=(
                audio_path,
                ata_path,
                assembly_key,
                openai_transcription_key,
                openai_post_key,
                claude_key,
                gemini_transcription_key,
                gemini_post_key,
                soniox_key,
                openrouter_key,
                selected_service,
                use_speaker_identification,
                transcription_model,
                post_model,
                generate_docx,
                post_processor,
            ),
            daemon=True
        )
        self.transcription_thread.start()

    def close_app(self):
        """Fecha a aplicação."""
        # (Código mantido como antes)
        print("Encerrando a aplicação...")
        self.running = False
        self.close()


    # NOVO: Função para Transcrição com Gemini
    def transcribe_with_gemini(self, file_path_or_url, destination_path, worker_signals, api_key_gemini, model_name="gemini-2.5-flash"):
        """Realiza a transcrição de áudio usando a API Gemini."""
        worker_signals.message.emit(f"⚙️ Preparando áudio para Gemini ({os.path.basename(file_path_or_url)})...")
        audio_file_handle = None
        uploaded_file = None
        temp_file_path = None
        is_local = not (file_path_or_url.startswith('http://') or file_path_or_url.startswith('https://'))

        try:
            # 1. Verificar duração do áudio antes do processamento
            if is_local:
                audio_duration_ms = get_audio_duration_from_path(file_path_or_url)
                audio_duration_minutes = audio_duration_ms / 60000
                worker_signals.message.emit(f"📊 Duração do áudio detectada: {ms_to_formatted_time(audio_duration_ms)} ({audio_duration_minutes:.1f} minutos)")
                
                # Verificar limites da API Gemini (1 hora para modelos 1M, 2 horas para 2M)
                if audio_duration_minutes > 60:
                    worker_signals.message.emit(f"⚠️ AVISO: Áudio de {audio_duration_minutes:.1f} min pode exceder limites da API Gemini (recomendado: <60 min)")
                    worker_signals.message.emit("ℹ️ A transcrição pode ser truncada ou falhar para áudios muito longos.")
            else:
                audio_duration_ms = get_audio_duration_from_url(file_path_or_url)
                audio_duration_minutes = audio_duration_ms / 60000
                worker_signals.message.emit(f"📊 Duração estimada do áudio: {ms_to_formatted_time(audio_duration_ms)} ({audio_duration_minutes:.1f} minutos)")

            # 2. Configurar API Key
            if not api_key_gemini:
                worker_signals.message.emit("❌ Erro: API Key do Gemini não fornecida.")
                return False
            
            worker_signals.message.emit("✅ Usando API Key do Gemini para transcrição.")
            
            # Configurar cliente do Gemini com a API key
            client = genai.Client(api_key=api_key_gemini)

            # 3. Preparar/Upload do Arquivo de Áudio
            if is_local:
                worker_signals.message.emit("⬆️ Fazendo upload do arquivo local para a API Gemini...")
                uploaded_file = client.files.upload(file=file_path_or_url)
                display_name = uploaded_file.display_name or os.path.basename(file_path_or_url)
                worker_signals.message.emit(f"✅ Upload concluído: {display_name}")
                audio_file_handle = uploaded_file
            else:
                worker_signals.message.emit("⬇️ Baixando áudio da URL para processamento...")
                try:
                    response = requests.get(file_path_or_url, stream=True, timeout=60)
                    response.raise_for_status()
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as temp_file:
                         for chunk in response.iter_content(chunk_size=8192):
                              temp_file.write(chunk)
                         temp_file_path = temp_file.name
                    worker_signals.message.emit(f"⬆️ Fazendo upload do arquivo baixado ({os.path.basename(temp_file_path)}) para a API Gemini...")
                    uploaded_file = client.files.upload(file=temp_file_path)
                    display_name = uploaded_file.display_name or os.path.basename(temp_file_path)
                    worker_signals.message.emit(f"✅ Upload concluído: {display_name}")
                    audio_file_handle = uploaded_file
                except requests.exceptions.RequestException as e:
                    worker_signals.message.emit(f"❌ Erro ao baixar áudio da URL {file_path_or_url}: {e}")
                    return False
                finally:
                     if temp_file_path and os.path.exists(temp_file_path):
                          os.unlink(temp_file_path)
                          print(f"Arquivo temporário {temp_file_path} removido.")

            if not audio_file_handle:
                 worker_signals.message.emit("❌ Erro: Falha ao preparar o handle do arquivo de áudio para Gemini.")
                 return False

            # 4. Chamar a API Gemini para Transcrição
            worker_signals.message.emit(f"🧠 Solicitando transcrição ao modelo Gemini ({model_name})...")
            worker_signals.message.emit(f"📊 Processando áudio de {audio_duration_minutes:.1f} minutos com Gemini...")

            prompt = """Transcreva este áudio em português brasileiro com as seguintes especificações:

1. Inclua timestamps precisos no formato [HH:MM:SS] para cada fala
2. Identifique e rotule diferentes interlocutores (Speaker 1, Speaker 2, etc.)
3. Mantenha a formatação clara com quebras de linha entre diferentes falas
4. Preserve pausas significativas e mudanças de tópico

Formato desejado:
[MM:SS] Speaker 1: [texto da fala]
[MM:SS] Speaker 2: [texto da fala]

Por favor, forneça uma transcrição completa e detalhada."""

            start_api_time = time.time()
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, audio_file_handle]
            )
            end_api_time = time.time()
            api_processing_time = end_api_time - start_api_time
            worker_signals.message.emit(f"⏱️ Resposta da API Gemini recebida em {api_processing_time:.2f} seg.")

            # 5. Processar Resposta e Salvar
            if response and hasattr(response, 'text') and response.text:
                transcribed_text = response.text.strip()
                worker_signals.message.emit(f"📄 Texto transcrito recebido (primeiros 100 chars): {transcribed_text[:100]}...")
                
                # Verificar se a transcrição parece completa comparando com a duração esperada
                transcribed_lines = transcribed_text.split('\n')
                non_empty_lines = [line for line in transcribed_lines if line.strip()]
                worker_signals.message.emit(f"📊 Transcrição contém {len(non_empty_lines)} linhas de texto.")
                
                # Análise básica de completude
                if audio_duration_minutes > 10 and len(non_empty_lines) < 10:
                    worker_signals.message.emit(f"⚠️ AVISO: Transcrição parece incompleta para áudio de {audio_duration_minutes:.1f} min (apenas {len(non_empty_lines)} linhas)")
                    worker_signals.message.emit("ℹ️ Possíveis causas: limite de contexto da API, áudio corrompido, ou falha no processamento.")

                # Salva o texto transcrito com os timestamps originais da API Gemini
                with open(destination_path, 'w', encoding='utf-8') as f:
                    f.write(transcribed_text)

                worker_signals.message.emit(f"✅ Transcrição com Gemini ({model_name}) salva em {os.path.basename(destination_path)}.")
                worker_signals.message.emit(f"📊 Resumo: Áudio {audio_duration_minutes:.1f}min → API {api_processing_time:.1f}s → {len(non_empty_lines)} linhas")
                return True
            else:
                error_detail = "Resposta vazia ou sem texto."
                if hasattr(response, 'prompt_feedback'):
                    error_detail += f" Feedback: {response.prompt_feedback}"
                if hasattr(response, 'candidates') and not response.candidates:
                     error_detail += " Nenhum candidato retornado."

                worker_signals.message.emit(f"❌ Erro na transcrição Gemini: Não foi possível extrair texto da resposta. {error_detail}")
                try:
                    with open(destination_path.replace('.txt', '_error.txt'), 'w', encoding='utf-8') as f:
                        f.write(f"Falha na transcrição Gemini.\nResposta recebida:\n{response}")
                except Exception:
                    pass
                return False

        except Exception as e:
            import traceback
            worker_signals.message.emit(f"❌ Erro inesperado durante a transcrição com Gemini: {e}")
            print(f"Traceback Gemini Transcription Error:\n{traceback.format_exc()}")
            return False
        finally:
             if uploaded_file:
                  try:
                       display_name = uploaded_file.display_name or "arquivo"
                       worker_signals.message.emit(f"🧹 Limpando arquivo da API Gemini: {display_name}...")
                       if uploaded_file.name:
                           client.files.delete(name=uploaded_file.name)
                           worker_signals.message.emit("✅ Limpeza concluída.")
                       else:
                           worker_signals.message.emit("⚠️ Aviso: Nome do arquivo da API Gemini indisponível para limpeza.")
                  except Exception as delete_error:
                       worker_signals.message.emit(f"⚠️ Aviso: Falha ao limpar arquivo da API Gemini ({uploaded_file.name}): {delete_error}")

    def transcribe_with_openrouter(self, file_path_or_url, destination_path, worker_signals, api_key_openrouter, model_name="openai/whisper-1"):
        """Realiza a transcrição de áudio usando a API OpenRouter (endpoint de transcrição)."""
        temp_file_path = None
        source_path = file_path_or_url
        try:
            if not api_key_openrouter:
                worker_signals.message.emit("❌ Erro: API Key do OpenRouter não fornecida.")
                return False

            is_url = file_path_or_url.startswith('http://') or file_path_or_url.startswith('https://')
            if is_url:
                worker_signals.message.emit("⬇️ Baixando áudio da URL para transcrição via OpenRouter...")
                response = requests.get(file_path_or_url, stream=True, timeout=60)
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as temp_file:
                    for chunk in response.iter_content(chunk_size=8192):
                        temp_file.write(chunk)
                    temp_file_path = temp_file.name
                source_path = temp_file_path

            if not os.path.exists(source_path):
                worker_signals.message.emit(f"❌ Erro: arquivo de áudio não encontrado em {source_path}")
                return False

            # O endpoint dedicado /audio/transcriptions (Whisper) só devolve texto corrido,
            # sem timestamps nem identificação de interlocutores. Para obter saída em
            # múltiplas linhas com falantes rotulados, usamos o endpoint /chat/completions
            # com um modelo capaz de áudio (input_audio em base64), instruído via prompt —
            # mesma abordagem usada na transcrição via Gemini.
            # Ref.: https://openrouter.ai/docs/guides/overview/multimodal/audio
            import base64
            audio_format = (os.path.splitext(source_path)[1].lstrip('.') or 'mp3').lower()
            # Normaliza extensões comuns para os formatos aceitos pela API.
            format_aliases = {'oga': 'ogg', 'mpeg': 'mp3', 'mpga': 'mp3'}
            audio_format = format_aliases.get(audio_format, audio_format)

            with open(source_path, 'rb') as audio_file:
                audio_b64 = base64.b64encode(audio_file.read()).decode('ascii')

            prompt = """Transcreva este áudio em português brasileiro com as seguintes especificações:

1. Inclua timestamps precisos no formato [HH:MM:SS] para cada fala
2. Identifique e rotule diferentes interlocutores (Speaker 1, Speaker 2, etc.)
3. Mantenha a formatação clara com quebras de linha entre diferentes falas
4. Preserve pausas significativas e mudanças de tópico

Formato desejado:
[MM:SS] Speaker 1: [texto da fala]
[MM:SS] Speaker 2: [texto da fala]

Por favor, forneça uma transcrição completa e detalhada. Responda APENAS com a transcrição, sem comentários adicionais."""

            request_headers = {
                "Authorization": f"Bearer {api_key_openrouter}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://kiwiscribe.local",
                "X-Title": "Kiwiscribe",
            }
            request_body = {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "input_audio", "input_audio": {"data": audio_b64, "format": audio_format}},
                        ],
                    }
                ],
            }

            max_retries = 3
            response_json = None
            for attempt in range(1, max_retries + 1):
                worker_signals.message.emit(f"🧠 OpenRouter transcrição: tentativa {attempt}/{max_retries} com modelo {model_name}...")
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=request_headers,
                    json=request_body,
                    timeout=600,
                )
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                    wait_time = attempt * 2
                    worker_signals.message.emit(f"⚠️ OpenRouter retornou {resp.status_code}. Nova tentativa em {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                resp.raise_for_status()
                response_json = resp.json() or {}
                break

            if not response_json:
                worker_signals.message.emit("❌ Erro: resposta vazia da API OpenRouter.")
                return False

            choices = response_json.get('choices') or []
            transcribed_text = ""
            if choices:
                message = choices[0].get('message') or {}
                content = message.get('content')
                # O conteúdo pode vir como string ou como lista de blocos (texto).
                if isinstance(content, list):
                    transcribed_text = "".join(
                        block.get('text', '') for block in content if isinstance(block, dict)
                    ).strip()
                elif isinstance(content, str):
                    transcribed_text = content.strip()

            if not transcribed_text:
                api_error = (response_json.get('error') or {}).get('message', '')
                worker_signals.message.emit(f"❌ Erro: OpenRouter não retornou texto transcrito. {api_error}".strip())
                return False

            with open(destination_path, 'w', encoding='utf-8') as output_file:
                output_file.write(transcribed_text)

            line_count = len([ln for ln in transcribed_text.split('\n') if ln.strip()])
            worker_signals.message.emit(f"✅ Transcrição com OpenRouter concluída: {os.path.basename(destination_path)} ({line_count} linhas).")
            return True

        except requests.exceptions.HTTPError as e:
            details = ""
            try:
                details = e.response.text if e.response is not None else ""
            except Exception:
                details = ""
            worker_signals.message.emit(f"❌ Erro HTTP OpenRouter na transcrição: {e}. {details}")
            return False
        except requests.exceptions.RequestException as e:
            worker_signals.message.emit(f"❌ Erro de conexão OpenRouter na transcrição: {e}")
            return False
        except openai.APIError as e:
            worker_signals.message.emit(f"❌ Erro da API OpenRouter na transcrição: {e}")
            return False
        except Exception as e:
            import traceback
            worker_signals.message.emit(f"❌ Erro inesperado na transcrição OpenRouter: {e}")
            print(f"Traceback OpenRouter Transcription Error:\n{traceback.format_exc()}")
            return False
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except Exception:
                    pass



    def transcribe_with_soniox(self, file_path_or_url, destination_path, worker_signals, api_key_soniox):
        """Realiza a transcricao de audio usando o SDK oficial do Soniox (corrige problema de espacamento em tokens pt-BR)."""
        try:
            # 1. Importar SDK oficial do Soniox (instalado via pip install soniox)
            try:
                from soniox import SonioxClient
                from soniox.types import CreateTranscriptionConfig
                worker_signals.message.emit("✅ Usando SDK oficial do Soniox para transcrição robusta.")
                use_sdk = True
            except ImportError:
                worker_signals.message.emit("⚠️ SDK do Soniox não instalado. Usando fallback REST manual.")
                use_sdk = False

            if not api_key_soniox:
                worker_signals.message.emit("❌ Erro: API Key do Soniox nao fornecida.")
                return False

            is_url = file_path_or_url.startswith('http://') or file_path_or_url.startswith('https://')

            # 2. ABORDAGEM PREFERIDA: SDK oficial (evita problema de espaçamento)
            if use_sdk:
                worker_signals.message.emit("🧠 Iniciando transcrição com SDK Soniox...")
                
                # Criar cliente do SDK
                client = SonioxClient(api_key=api_key_soniox)
                
                # Configurar parâmetros otimizados para Português
                config = CreateTranscriptionConfig(
                    model="stt-async-v4",
                    enable_speaker_diarization=True,
                    enable_language_identification=False,
                    language_hints=["pt"],  # Código oficial conforme documentação Soniox
                    language_hints_strict=True
                )
                
                # Executar transcrição baseado na fonte
                if is_url:
                    worker_signals.message.emit(f"🔗 Transcrevendo áudio da URL com SDK Soniox...")
                    result = client.stt.transcribe_from_url(
                        audio_url=file_path_or_url,
                        config=config
                    )
                    # Aguardar conclusão
                    result = client.stt.wait(result.id)
                elif os.path.isfile(file_path_or_url):
                    worker_signals.message.emit(f"⬆️ Enviando arquivo para Soniox via SDK...")
                    # SDK gerencia upload automaticamente
                    result = client.stt.transcribe_from_file(
                        file=file_path_or_url,
                        config=config
                    )
                    # Aguardar conclusão
                    worker_signals.message.emit(f"🕒 Aguardando conclusão da transcrição (ID: {result.id})...")
                    result = client.stt.wait(result.id)
                else:
                    worker_signals.message.emit(f"❌ Erro: Arquivo local não encontrado: {file_path_or_url}")
                    return False
                
                # 3. Obter transcript já renderizado corretamente pelo SDK
                worker_signals.message.emit("📥 Baixando transcript renderizado do Soniox...")
                transcript_result = client.stt.get_transcript(result.id)
                
                # Extrair tokens já processados
                tokens = transcript_result.tokens if hasattr(transcript_result, 'tokens') else []
                transcript_text_fallback = transcript_result.text if hasattr(transcript_result, 'text') else ""
                
                # 4. Construir segmentos por interlocutor preservando o texto dos tokens do SDK
                segments = []
                current_speaker = None
                current_start_ms = None
                current_text_parts = []
                previous_token_end_ms = None

                def _normalize_segment_text(text):
                    # Normalização mínima: remove espaços antes de pontuação e excesso de espaços
                    text = re.sub(r'\s+([.,!?;:\)])', r'\1', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    return text
                
                for token_obj in tokens:
                    # Acessar atributos do objeto Token do SDK
                    is_audio_event = getattr(token_obj, 'is_audio_event', False)
                    if is_audio_event:
                        continue
                    
                    token_text = getattr(token_obj, 'text', '')
                    if not token_text or not token_text.strip():
                        continue
                    
                    start_ms = getattr(token_obj, 'start_ms', None)
                    speaker = getattr(token_obj, 'speaker', None)
                    
                    if start_ms is None:
                        continue
                    
                    token_end_ms = getattr(token_obj, 'end_ms', None)
                    pause_from_previous_ms = None
                    if previous_token_end_ms is not None:
                        pause_from_previous_ms = start_ms - previous_token_end_ms

                    # Detectar mudança de interlocutor ou pausa longa entre tokens consecutivos
                    should_split_segment = (
                        current_speaker is None
                        or speaker != current_speaker
                        or (pause_from_previous_ms is not None and pause_from_previous_ms > 1800)
                    )

                    if should_split_segment:
                        
                        # Finalizar segmento anterior
                        if current_text_parts:
                            full_text = ''.join(current_text_parts)
                            full_text = _normalize_segment_text(full_text)
                            
                            segments.append((
                                current_start_ms or 0,
                                f"Interlocutor {current_speaker}" if current_speaker else "Interlocutor Desconhecido",
                                full_text
                            ))
                        
                        # Iniciar novo segmento
                        current_text_parts = [token_text]
                        current_speaker = speaker
                        current_start_ms = start_ms
                    else:
                        # Continuar segmento atual
                        current_text_parts.append(token_text)

                    # Atualiza referência temporal do token anterior para cálculo de pausa
                    if token_end_ms is not None:
                        previous_token_end_ms = token_end_ms
                    else:
                        previous_token_end_ms = start_ms
                
                # Finalizar último segmento
                if current_text_parts:
                    full_text = ''.join(current_text_parts)
                    full_text = _normalize_segment_text(full_text)
                    segments.append((
                        current_start_ms or 0,
                        f"Interlocutor {current_speaker}" if current_speaker else "Interlocutor Desconhecido",
                        full_text
                    ))
                
                # Fallback: se não houver tokens, usar texto simples
                if not segments and transcript_text_fallback:
                    segments = [(0, "Interlocutor Soniox", transcript_text_fallback)]
            
            # 3. FALLBACK: Implementação REST manual (mantida para compatibilidade, mas desencorajada)
            else:
                worker_signals.message.emit("⚠️ Usando implementação REST manual do Soniox (pode ter problemas de espaçamento em pt-BR).")
                segments = self._transcribe_with_soniox_rest_fallback(
                    file_path_or_url, api_key_soniox, is_url, worker_signals
                )
                if segments is None:
                    return False
            
            # 4. Salvar resultado
            if not segments:
                worker_signals.message.emit("❌ Erro: Transcript Soniox vazio (nenhum segmento gerado).")
                return False
            
            with open(destination_path, 'w', encoding='utf-8') as f:
                for start_ms, speaker_label, text in segments:
                    line = f"[{ms_to_formatted_time(start_ms)}] {speaker_label}: {text}\n"
                    f.write(line)
            
            worker_signals.message.emit(f"✅ Transcricao Soniox salva em {os.path.basename(destination_path)}.")
            worker_signals.message.emit(f"📊 Resumo: {len(segments)} segmentos de fala identificados.")
            return True

        except Exception as e:
            import traceback
            worker_signals.message.emit(f"❌ Erro inesperado na transcricao Soniox: {e}")
            print(f"Traceback Soniox Error:\n{traceback.format_exc()}")
            return False

    def _transcribe_with_soniox_rest_fallback(self, file_path_or_url, api_key_soniox, is_url, worker_signals):
        """Fallback REST manual caso SDK não esteja disponível (manter compatibilidade)."""
        base_url = "https://api.soniox.com/v1"
        headers = {"Authorization": f"Bearer {api_key_soniox}"}
        file_id = None
        transcription_id = None
        session = requests.Session()
        
        def request_with_retry(method, url, *, attempts=3, retry_delay=2, timeout=60, **kwargs):
            current_delay = retry_delay
            for attempt in range(1, attempts + 1):
                try:
                    return session.request(method, url, timeout=timeout, **kwargs)
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    if attempt >= attempts:
                        raise
                    worker_signals.message.emit(
                        f"⚠️ Falha de rede Soniox ({type(e).__name__}) na tentativa {attempt}/{attempts}. "
                        f"Tentando novamente em {current_delay}s..."
                    )
                    time.sleep(current_delay)
                    current_delay = min(current_delay * 2, 10)
            raise requests.exceptions.RequestException("Falha de rede ao chamar API Soniox apos tentativas.")
        
        try:
            # Upload de arquivo se necessário
            if not is_url and os.path.isfile(file_path_or_url):
                worker_signals.message.emit("⬆️ Enviando arquivo para Soniox (REST)...")
                with open(file_path_or_url, 'rb') as audio_file:
                    response = request_with_retry(
                        "POST",
                        f"{base_url}/files",
                        headers=headers,
                        files={"file": audio_file},
                        timeout=600
                    )
                if response.status_code != 201:
                    worker_signals.message.emit(f"❌ Erro no upload Soniox (Status {response.status_code}): {response.text}")
                    return None
                file_id = response.json().get("id")
                if not file_id:
                    worker_signals.message.emit("❌ Erro: Soniox nao retornou file_id.")
                    return None
                worker_signals.message.emit(f"✅ Upload Soniox concluido. File ID: {file_id}")
            
            # Criar transcrição
            payload = {
                "model": "stt-async-v4",
                "enable_speaker_diarization": True,
                "enable_language_identification": True  # Auto-detecta idioma (REST API rejeita language_hints)
                # language_hints removido - REST API tem validação diferente do SDK
            }
            if is_url:
                payload["audio_url"] = file_path_or_url
            else:
                if not file_id:
                    worker_signals.message.emit("❌ Erro: arquivo local invalido para upload Soniox.")
                    return None
                payload["file_id"] = file_id
            
            worker_signals.message.emit("🧠 Criando transcricao async no Soniox (REST)...")
            response = request_with_retry(
                "POST",
                f"{base_url}/transcriptions",
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
                timeout=120
            )
            if response.status_code != 201:
                worker_signals.message.emit(f"❌ Erro ao criar transcricao Soniox (Status {response.status_code}): {response.text}")
                return None
            
            transcription = response.json()
            transcription_id = transcription.get("id")
            status = transcription.get("status")
            if not transcription_id:
                worker_signals.message.emit("❌ Erro: Soniox nao retornou transcription_id.")
                return None
            
            worker_signals.message.emit(f"🕒 Transcricao Soniox criada (Status: {status}). Aguardando conclusao...")
            
            # Polling de status
            max_wait_seconds = 60 * 60
            poll_interval = 2
            waited = 0
            last_status = status
            status_payload = {}
            while status in ("queued", "processing") and waited < max_wait_seconds:
                time.sleep(poll_interval)
                waited += poll_interval
                poll_interval = min(poll_interval + 1, 10)
                status_response = request_with_retry(
                    "GET",
                    f"{base_url}/transcriptions/{transcription_id}",
                    headers=headers,
                    timeout=45,
                    attempts=2,
                    retry_delay=1
                )
                if status_response.status_code != 200:
                    worker_signals.message.emit(f"⚠️ Aviso: Falha ao consultar status Soniox (Status {status_response.status_code}). Tentando novamente...")
                    continue
                status_payload = status_response.json()
                status = status_payload.get("status")
                if status != last_status:
                    worker_signals.message.emit(f"🔄 Status Soniox: {status}")
                    last_status = status
            
            if status != "completed":
                error_message = "Timeout aguardando transcricao Soniox." if waited >= max_wait_seconds else "Falha na transcricao Soniox."
                if status == "error":
                    error_message = status_payload.get("error_message") or error_message
                worker_signals.message.emit(f"❌ Erro: {error_message}")
                return None
            
            # Baixar transcript
            worker_signals.message.emit("📥 Baixando transcript do Soniox (REST)...")
            transcript_response = request_with_retry(
                "GET",
                f"{base_url}/transcriptions/{transcription_id}/transcript",
                headers=headers,
                timeout=120
            )
            if transcript_response.status_code != 200:
                worker_signals.message.emit(f"❌ Erro ao obter transcript Soniox (Status {transcript_response.status_code}): {transcript_response.text}")
                return None
            
            transcript_payload = transcript_response.json()
            transcript_text = transcript_payload.get("text", "").strip()
            
            # Usar texto simples (pior qualidade, mas funcional)
            worker_signals.message.emit("⚠️ Fallback REST: usando texto simples (sem diarização granular).")
            if transcript_text:
                return [(0, "Interlocutor Soniox", transcript_text)]
            else:
                return []
        
        except requests.exceptions.RequestException as e:
            worker_signals.message.emit(f"❌ Erro de conexao com Soniox (REST): {e}")
            return None
        except Exception as e:
            import traceback
            worker_signals.message.emit(f"❌ Erro inesperado no fallback REST do Soniox: {e}")
            print(f"Traceback Soniox REST Fallback Error:\n{traceback.format_exc()}")
            return None
        finally:
            if file_id:
                try:
                    session.delete(
                        f"{base_url}/files/{file_id}",
                        headers=headers,
                        timeout=30
                    )
                except Exception:
                    pass
            session.close()



    def perform_transcription_workflow(
        self,
        file_path_or_url,
        ata_path,
        api_key_assembly,
        api_key_openai_transcription,
        api_key_openai_post,
        api_key_claude,
        api_key_gemini_transcription,
        api_key_gemini_post,
        api_key_soniox,
        api_key_openrouter,
        selected_service,
        use_speaker_identification=False,
        transcription_model=None,
        post_model=None,
        generate_docx=False,
        post_processor=None,
    ):
        """Executa a transcrição e o pós-processamento (roda em background). use_speaker_identification: usar Speaker Identification da AssemblyAI com nomes da ata."""
        # (Início da função igual à versão anterior: validação, prep. destino, extração ata)
        start_time_workflow = time.time()
        full_destination_path = None # Caminho do arquivo de transcrição inicial
        final_output_path = None # Caminho do arquivo final (pode ser o mesmo ou o formatado)

        try:
            # --- 1. Validação do Áudio e Preparação do Destino ---
            self.worker_signals.message.emit(f"🔄 Validando fonte de áudio/texto: {os.path.basename(file_path_or_url)}")
            is_url = file_path_or_url.startswith('http://') or file_path_or_url.startswith('https://')
            base_name = ""
            output_dir = get_download_dir() # Padrão

            if is_url:
                try:
                    parsed_url = urlparse(file_path_or_url)
                    url_path = parsed_url.path
                    base_name = os.path.basename(url_path) if url_path and '.' in os.path.basename(url_path) else "audio_remoto"
                    base_name = os.path.splitext(base_name)[0]
                    duration = get_audio_duration_from_url(file_path_or_url)
                    self.worker_signals.message.emit(f"🔗 Fonte de áudio é URL. Duração estimada: {ms_to_formatted_time(duration)}.")
                except Exception as e:
                     self.worker_signals.message.emit(f"⚠️ Aviso: Não foi possível validar URL ou estimar duração: {e}. Continuando...")
                     base_name = "audio_remoto_validacao_falhou"
                     duration = 0
            else: # Arquivo local
                 if os.path.isfile(file_path_or_url):
                      output_dir = os.path.dirname(file_path_or_url)
                      base_name = os.path.splitext(os.path.basename(file_path_or_url))[0]
                      if not file_path_or_url.lower().endswith('.txt'):
                          duration = get_audio_duration_from_path(file_path_or_url)
                          estimate = get_estimated_transcription_time(duration)
                          self.worker_signals.message.emit(f"📄 Fonte de áudio é arquivo local. Duração: {ms_to_formatted_time(duration)}. Estimativa conclusão transcrição: ~{estimate}.")
                      else:
                          if selected_service == "JustGenerateDocx":
                              self.worker_signals.message.emit("📄 Fonte é arquivo de texto local (geração direta de DOCX).")
                          else:
                              self.worker_signals.message.emit("📄 Fonte é arquivo de texto local (Pós-processamento direto).")
                 else:
                      self.worker_signals.error.emit(f"❌ Erro fatal: Arquivo local não encontrado em '{file_path_or_url}'.")
                      return

            # Se for modo "Apenas Pós-processar", o base_name vem do arquivo de transcrição
            
            is_text_input = file_path_or_url.lower().endswith('.txt')
            
            # Define o nome do arquivo de transcrição inicial
            safe_base_name = re.sub(r'[\\/*?:"<>|\s]+', '_', base_name)
            transcription_model = transcription_model or self._selected_transcription_model()
            post_model = post_model or self._selected_post_model()
            transcription_suffix = f"_tts_{self._sanitize_model_tag(transcription_model)}"
            post_suffix = f"_post_{self._sanitize_model_tag(post_model)}"
            
            if is_text_input:
                 # Se for input de texto, o full_destination_path é o próprio arquivo (para leitura)
                 full_destination_path = file_path_or_url
                 transcript_file_name = os.path.basename(file_path_or_url)
                 self.worker_signals.message.emit(f"📄 Usando arquivo de transcrição existente: {full_destination_path}")
            else:
                transcript_file_name = safe_base_name + "_transcrito" + transcription_suffix + ".txt"
                full_destination_path = os.path.join(output_dir, transcript_file_name)
                self.worker_signals.message.emit(f"💾 Arquivo de transcrição inicial será salvo como: {full_destination_path}")
                
            final_output_path = full_destination_path 

            # Cria/Limpa arquivo de destino inicial APENAS SE NÃO FOR INPUT DE TEXTO
            if not is_text_input:
                try:
                    with open(full_destination_path, 'w', encoding='utf-8') as f:
                         f.write("")
                except IOError as e:
                     self.worker_signals.error.emit(f"❌ Erro fatal ao criar/limpar arquivo de destino '{full_destination_path}': {e}")
                     return

            # --- 2. Extração da Ata (se fornecida) ---
            ata_info = {}
            if ata_path:
                self.worker_signals.message.emit(f"⚖️ Processando arquivo da ata: {os.path.basename(ata_path)}...")
                ata_extraction_result = extract_info_from_ata(ata_path)
                if isinstance(ata_extraction_result, str) and ata_extraction_result.startswith("Erro"):
                     self.worker_signals.message.emit(f"⚠️ {ata_extraction_result}. O pós-processamento pode ser menos preciso.")
                     ata_info = {"error": ata_extraction_result}
                elif isinstance(ata_extraction_result, dict):
                     ata_info = ata_extraction_result
                     formatted_ata = format_ata_info(ata_info)
                     self.worker_signals.message.emit(f"📄 Informações da ata extraídas:\n---\n{formatted_ata}\n---")
                else:
                     self.worker_signals.message.emit(f"⚠️ Aviso: Resultado inesperado da extração da ata.")
            else:
                self.worker_signals.message.emit("ℹ️ Nenhum arquivo de ata fornecido.")
                ata_info = {"info": "Nenhuma ata fornecida."}


            # --- 3. Transcrição (AssemblyAI, OpenAI ou Gemini) --- MODIFICADO
            transcript_success = False

            if selected_service in ("JustPostProcess", "JustGenerateDocx"):
                if selected_service == "JustGenerateDocx":
                    self.worker_signals.message.emit("⏩ Pulando transcrição e pós-processamento (Modo Apenas Gerar DOCX selecionado).")
                else:
                    self.worker_signals.message.emit("⏩ Pulando etapa de transcrição (Modo Apenas Pós-processar selecionado).")
                transcript_success = True
            else:
                self.worker_signals.message.emit(f"🎙️ Iniciando transcrição com {selected_service}...")
                start_transcription_time = time.time()

            if selected_service == "AssemblyAI":
                # (Lógica AssemblyAI mantida como antes)
                try:
                    num_interlocutors_str = self.num_input.text()
                    num_interlocutors = int(num_interlocutors_str) if num_interlocutors_str.isdigit() else 0
                    effective_assembly_key = api_key_assembly if api_key_assembly else self.saved_keys.get('assembly_ai')
                    if not effective_assembly_key:
                        self.worker_signals.message.emit(
                            "❌ Erro: API Key da AssemblyAI não configurada. "
                            "Informe-a na interface ou no arquivo .transcription_config.json (campo 'assembly_ai')."
                        )
                        raise ValueError("API Key da AssemblyAI ausente.")
                    aai.settings.api_key = effective_assembly_key

                    self.worker_signals.message.emit(f"🗣️ Configurando AssemblyAI (Interlocutores: {'Automático' if num_interlocutors == 0 else num_interlocutors})...")
                    boost_terms = ["juiz", "juíza", "excelência", "reclamante", "reclamada", "preposto", "preposta", "advogado", "advogada", "testemunha", "depoimento", "contradita", "indeferido", "deferido", "pela ordem", "questão de ordem", "autos", "sentença", "acórdão", "liminar", "tutela", "mérito", "ônus da prova", "cartão de ponto", "horas extras", "intervalo", "verbas rescisórias"]
                    config_params = {
                        "speech_models": [transcription_model],
                        "language_code": "pt", "speaker_labels": True }
                    # word_boost/boost_param são incompatíveis com os modelos Universal-3;
                    # estes usam keyterms_prompt para destacar termos jurídicos frequentes.
                    if str(transcription_model).startswith("universal-3"):
                        config_params["keyterms_prompt"] = boost_terms
                    else:
                        config_params["word_boost"] = boost_terms
                        config_params["boost_param"] = "high"
                    if 0 < num_interlocutors <= 15: config_params["speakers_expected"] = num_interlocutors
                    elif num_interlocutors > 15: self.worker_signals.message.emit("⚠️ Aviso: AssemblyAI suporta no máximo 15 interlocutores. Usando detecção automática.")

                    # Speaker Identification: nomes da ata como known_values (doc: https://www.assemblyai.com/docs/speech-understanding/speaker-identification)
                    if use_speaker_identification:
                        known_values = get_speaker_identification_known_values(ata_info)
                        if known_values:
                            config_params["speech_understanding"] = {
                                "request": {
                                    "speaker_identification": {
                                        "speaker_type": "name",
                                        "known_values": known_values
                                    }
                                }
                            }
                            self.worker_signals.message.emit(f"🔍 Speaker Identification ativado com {len(known_values)} nomes da ata: {', '.join(known_values[:5])}{'...' if len(known_values) > 5 else ''}")
                        else:
                            self.worker_signals.message.emit("⚠️ Speaker Identification marcado, mas não foi possível obter nomes da ata (ata ausente ou sem dados). Transcrição sem identificação por nome.")

                    config = aai.TranscriptionConfig(**config_params)
                    transcriber = aai.Transcriber()
                    transcript = transcriber.transcribe(file_path_or_url, config=config)

                    if transcript.status == aai.TranscriptStatus.error: raise RuntimeError(f"Erro AssemblyAI: {transcript.error}")
                    if transcript.status != aai.TranscriptStatus.completed: raise RuntimeError(f"Transcrição AssemblyAI não completou (Status: {transcript.status}).")

                    if transcript.utterances:
                         utterance_count = 0
                         with open(full_destination_path, 'w', encoding='utf-8') as file:
                              for utterance in transcript.utterances:
                                   speaker = f" Interlocutor {utterance.speaker}" if utterance.speaker else " Interlocutor Desconhecido"
                                   start_time_f = ms_to_formatted_time(utterance.start)
                                   line = f"[{start_time_f}]{speaker}: {utterance.text}\n"
                                   file.write(line)
                                   utterance_count += 1
                         if utterance_count > 0:
                             self.worker_signals.message.emit(f"✅ Transcrição com AssemblyAI concluída ({utterance_count} falas).")
                             transcript_success = True
                         else:
                             self.worker_signals.message.emit("⚠️ Aviso: AssemblyAI concluiu, mas não retornou falas.")
                             transcript_success = False
                    else:
                         self.worker_signals.message.emit("⚠️ Aviso: AssemblyAI completou sem erros, mas sem 'utterances'.")
                         transcript_success = False
                except Exception as e:
                    import traceback
                    self.worker_signals.message.emit(f"❌ Erro durante a transcrição com AssemblyAI: {str(e)}")
                    print(f"Traceback AssemblyAI Error:\n{traceback.format_exc()}")
                    transcript_success = False

            elif selected_service == "gpt-4o-transcribe":
                # (Lógica OpenAI GPT com melhor tratamento de erros)
                try:
                    # Verificar tamanho do arquivo antes do envio
                    file_size = os.path.getsize(file_path_or_url)
                    max_size_mb = 25  # Limite da OpenAI é 25MB
                    if file_size > max_size_mb * 1024 * 1024:
                        self.worker_signals.message.emit(f"❌ Erro: Arquivo muito grande ({file_size / (1024*1024):.1f}MB). Limite da OpenAI: {max_size_mb}MB.")
                        transcript_success = False
                    else:
                        client = OpenAI(api_key=api_key_openai_transcription)
                        self.worker_signals.message.emit(f"🗣️ Enviando áudio para OpenAI {transcription_model}... (Tamanho: {file_size / (1024*1024):.1f}MB)")
                        
                        # Implementar retry com backoff exponencial para erros 500
                        max_retries = 3
                        retry_count = 0
                        
                        while retry_count < max_retries:
                            try:
                                with open(file_path_or_url, 'rb') as audio_file:
                                    response = client.audio.transcriptions.create(
                                        model=transcription_model, 
                                        file=audio_file, 
                                        language="pt",
                                        response_format="json"
                                    )
                                break  # Sucesso, sai do loop de retry
                                
                            except openai.APIStatusError as status_error:
                                if status_error.status_code == 500:
                                    retry_count += 1
                                    if retry_count < max_retries:
                                        wait_time = 2 ** retry_count  # Backoff exponencial: 2, 4, 8 segundos
                                        self.worker_signals.message.emit(f"⚠️ Erro 500 da OpenAI (tentativa {retry_count}/{max_retries}). Aguardando {wait_time}s antes de tentar novamente...")
                                        time.sleep(wait_time)
                                    else:
                                        self.worker_signals.message.emit(f"❌ Erro 500 da OpenAI persistiu após {max_retries} tentativas. Possíveis causas: servidor sobrecarregado, arquivo corrompido ou formato incompatível.")
                                        transcript_success = False
                                        break
                                else:
                                    # Outros erros de status, não tenta novamente
                                    raise status_error
                        
                        if retry_count < max_retries:  # Sucesso
                            # With "json" format, the response has a different structure
                            if response and hasattr(response, 'text') and response.text:
                                # Simple format - just the transcribed text without timestamps
                                transcribed_text = response.text.strip()
                                with open(full_destination_path, 'w', encoding='utf-8') as file:
                                    # Since we don't have segments with "json" format, create a single entry
                                    line = f"[00:00:00 --> 00:00:00] Interlocutor OpenAI: {transcribed_text}\n"
                                    file.write(line)
                                
                                self.worker_signals.message.emit(f"✅ Transcrição com OpenAI {transcription_model} concluída.")
                                transcript_success = True
                            else:
                                self.worker_signals.message.emit(f"⚠️ Aviso: Resposta do OpenAI gpt-4o-transcribe inválida ou sem texto.")
                                transcript_success = False
                        
                except openai.RateLimitError as e:
                     self.worker_signals.message.emit(f"❌ Erro de limite de taxa da API OpenAI: Muitas requisições. Aguarde alguns minutos e tente novamente. ({e})")
                     transcript_success = False
                except openai.AuthenticationError as e:
                     self.worker_signals.message.emit(f"❌ Erro de autenticação da API OpenAI: Verifique se sua API Key está correta e ativa. ({e})")
                     transcript_success = False
                except openai.APITimeoutError as e:
                     self.worker_signals.message.emit(f"❌ Erro de timeout da API OpenAI: O arquivo pode ser muito grande ou a conexão está lenta. ({e})")
                     transcript_success = False
                except openai.APIConnectionError as e:
                     self.worker_signals.message.emit(f"❌ Erro de conexão com a API OpenAI: Verifique sua conexão com a internet. ({e})")
                     transcript_success = False
                except openai.BadRequestError as e:
                     self.worker_signals.message.emit(f"❌ Erro na requisição à API OpenAI: Formato de arquivo pode ser incompatível. Tente converter para MP3, WAV ou M4A. ({e})")
                     transcript_success = False
                except openai.APIStatusError as e:
                     if e.status_code == 500:
                         self.worker_signals.message.emit(f"❌ Erro interno do servidor OpenAI (500): Tente novamente em alguns minutos. Se persistir, o problema pode ser no servidor da OpenAI.")
                     else:
                         self.worker_signals.message.emit(f"❌ Erro da API OpenAI (Status {e.status_code}): {e.message}")
                     transcript_success = False
                except FileNotFoundError:
                     self.worker_signals.message.emit(f"❌ Erro: Arquivo de áudio não encontrado: {file_path_or_url}")
                     transcript_success = False
                except Exception as e:
                     import traceback
                     self.worker_signals.message.emit(f"❌ Erro inesperado durante a transcrição com OpenAI {transcription_model}: {str(e)}")
                     print(f"Traceback gpt-4o-transcribe Error:\n{traceback.format_exc()}")
                     transcript_success = False

            elif selected_service == "Gemini":
                 # Chama a nova função de transcrição Gemini
                 transcript_success = self.transcribe_with_gemini(
                     file_path_or_url,
                     full_destination_path,
                     self.worker_signals,
                     api_key_gemini_transcription,
                     transcription_model
                 )
                 # Se falhar, a função transcribe_with_gemini já terá emitido a mensagem de erro.

            elif selected_service == "OpenRouter":
                 transcript_success = self.transcribe_with_openrouter(
                     file_path_or_url,
                     full_destination_path,
                     self.worker_signals,
                     api_key_openrouter,
                     transcription_model,
                 )

            elif selected_service == "Soniox":
                 transcript_success = self.transcribe_with_soniox(
                     file_path_or_url,
                     full_destination_path,
                     self.worker_signals,
                     api_key_soniox
                 )


            end_transcription_time = time.time()
            if selected_service not in ("JustPostProcess", "JustGenerateDocx") and 'start_transcription_time' in locals():
                self.worker_signals.message.emit(f"⏱️ Tempo de transcrição ({selected_service}): {end_transcription_time - start_transcription_time:.2f} segundos.")



            # --- 4. Pós-processamento (Claude, OpenAI ou Gemini) ---
            if transcript_success:
                # Adiciona informação sobre a transcrição Gemini melhorada
                if selected_service == "Gemini" and post_processor:
                    self.worker_signals.message.emit("ℹ️ Info: Transcrição Gemini configurada para incluir timestamps e diarização de interlocutores.")

                # post_processor é capturado no thread da GUI em start_transcription;
                # JustGenerateDocx nunca pós-processa.
                if selected_service == "JustGenerateDocx":
                    post_processor = None

                if post_processor:
                      self.worker_signals.message.emit(f"⚙️ Iniciando pós-processamento com {post_processor}...")
                      start_post_time = time.time()
                      result = None
                      post_output_path = None
                      if not is_text_input:
                           post_output_name = safe_base_name + "_transcrito" + transcription_suffix + post_suffix + ".txt"
                           post_output_path = os.path.join(output_dir, post_output_name)
                      else:
                           input_base = os.path.splitext(os.path.basename(full_destination_path))[0]
                           post_output_path = os.path.join(output_dir, input_base + post_suffix + ".txt")
                      if post_processor == "Claude":
                           result = process_transcript_with_claude(full_destination_path, ata_info, api_key_claude, post_output_path, post_model)
                      elif post_processor == "OpenAI":
                           result = process_transcript_with_openai(full_destination_path, ata_info, api_key_openai_post, post_output_path, post_model)
                      elif post_processor == "Gemini":
                           result = process_transcript_with_gemini(
                               full_destination_path,
                               ata_info,
                               api_key_gemini_post,
                               post_output_path,
                               self.worker_signals.message.emit,
                               post_model,
                           )
                      elif post_processor == "OpenRouter":
                           result = process_transcript_with_openrouter(
                               full_destination_path,
                               ata_info,
                               api_key_openrouter,
                               post_output_path,
                               post_model,
                           )

                      end_post_time = time.time()
                      self.worker_signals.message.emit(f"⏱️ Tempo de pós-processamento ({post_processor}): {end_post_time - start_post_time:.2f} segundos.")

                      if isinstance(result, str) and result.startswith("Erro"):
                           self.worker_signals.message.emit(f"⚠️ Pós-processamento com {post_processor} falhou: {result}. O arquivo '{transcript_file_name}' contém a transcrição base.")
                           # Mantém final_output_path como o arquivo transcrito
                      elif isinstance(result, str) and os.path.exists(result):
                           self.worker_signals.message.emit(f"✅ Pós-processamento com {post_processor} concluído: {os.path.basename(result)}")
                           final_output_path = result # Atualiza para o arquivo formatado
                      else:
                           # Caso inesperado
                            self.worker_signals.message.emit(f"⚠️ Resultado inesperado do pós-processamento com {post_processor}. Verifique os logs.")

                else: # self.use_none_radio.isChecked()
                      self.worker_signals.message.emit("ℹ️ Nenhum pós-processamento selecionado.")
                      # final_output_path já é o full_destination_path

                docx_output_path = None
                if generate_docx:
                    if not DOCX_GENERATOR_AVAILABLE:
                        self.worker_signals.message.emit("⚠️ Geração de DOCX solicitada, mas módulo indisponível.")
                    else:
                        txt_source_for_docx = final_output_path if final_output_path and os.path.exists(final_output_path) else full_destination_path
                        if not txt_source_for_docx or not os.path.exists(txt_source_for_docx):
                            self.worker_signals.message.emit("⚠️ TXT final não encontrado para gerar DOCX.")
                        else:
                            ata_pdf_path = ata_path if ata_path and ata_path.lower().endswith('.pdf') else None
                            if not ata_pdf_path:
                                self.worker_signals.message.emit("⚠️ Ata não informada (ou não PDF). DOCX será gerado sem metadados da ata.")
                            self.worker_signals.message.emit("📝 Iniciando geração do DOCX...")
                            try:
                                docx_output_path = generate_word_document(
                                    txt_source_for_docx,
                                    ata_pdf_path=ata_pdf_path,
                                    output_dir=os.path.dirname(txt_source_for_docx),
                                    logger=lambda msg: self.worker_signals.message.emit(f"📄 DOCX: {msg}"),
                                )
                                self.worker_signals.message.emit(f"✅ DOCX gerado com sucesso: {docx_output_path}")
                            except Exception as e:
                                self.worker_signals.message.emit(f"⚠️ Falha ao gerar DOCX: {e}")

                 # Mensagem final de sucesso
                total_time = time.time() - start_time_workflow
                self.worker_signals.message.emit(f"\n🎉 Processo concluído com sucesso em {total_time:.2f} segundos!")
                self.worker_signals.message.emit(f"📄 Arquivo final: {final_output_path}")

                # Mensagem final com detalhes dos arquivos
                if transcript_success:
                    self.worker_signals.message.emit("\n📁 Arquivos gerados:")
                    item_index = 1
                    
                    if os.path.exists(full_destination_path):
                        self.worker_signals.message.emit(f"{item_index}. Transcrição inicial: {os.path.basename(full_destination_path)}")
                        self.worker_signals.message.emit(f"   Local: {os.path.dirname(full_destination_path)}")
                        item_index += 1
                    
                    if final_output_path != full_destination_path and os.path.exists(final_output_path):
                        self.worker_signals.message.emit(f"{item_index}. Arquivo formatado: {os.path.basename(final_output_path)}")
                        self.worker_signals.message.emit(f"   Local: {os.path.dirname(final_output_path)}")
                        item_index += 1

                    if generate_docx and 'docx_output_path' in locals() and docx_output_path and os.path.exists(docx_output_path):
                        self.worker_signals.message.emit(f"{item_index}. Documento DOCX: {os.path.basename(docx_output_path)}")
                        self.worker_signals.message.emit(f"   Local: {os.path.dirname(docx_output_path)}")
                        item_index += 1
                    
                    # Adiciona informações sobre o log
                    log_dir = get_log_dir()
                    latest_log = os.path.basename(self.current_log_file) if self.current_log_file else "(não disponível)"
                    self.worker_signals.message.emit(f"{item_index}. Arquivo de log: {latest_log}")
                    self.worker_signals.message.emit(f"   Local: {log_dir}")

            else: # transcript_success == False
                 self.worker_signals.message.emit("❌ Processo interrompido devido a erro na transcrição.")

        except Exception as e:
            import traceback
            error_msg = f"❌ Erro inesperado no fluxo de trabalho: {str(e)}"
            self.worker_signals.message.emit(error_msg)
            print(f"Traceback Workflow Error:\n{traceback.format_exc()}")
        finally:
            self.worker_signals.finished.emit()


    # --- Slots (update_message_box, on_transcription_finished, on_transcription_error, check_transcription_status) ---
    # (Mantidos como na versão anterior)
    def update_message_box(self, message):
        """Adiciona mensagem à caixa de texto na UI (thread-safe) e rola para o final."""
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        current_text = self.message_box.toPlainText()
        # Adiciona newline se a caixa não estiver vazia, para separar mensagens
        prefix = "\n" if current_text else ""
        formatted_message = f"{prefix}{timestamp} {message}"
        self.message_box.append(formatted_message) # append adiciona newline automaticamente

        # Salva a mensagem no arquivo de log
        try:
            log_dir = get_log_dir()
            log_file = self.current_log_file
            if not log_file:
                fallback_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                suffix = self.current_run_suffix if self.current_run_suffix else "_tts_na_post_na"
                log_file = os.path.join(log_dir, f"kiwiscribe_log_{fallback_timestamp}{suffix}.txt")
                self.current_log_file = log_file
            
            # Se for a primeira mensagem, cria o arquivo com cabeçalho
            if not os.path.exists(log_file):
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(f"=== Log do Kiwiscribe - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ===\n\n")
            
            # Adiciona a mensagem ao arquivo
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(formatted_message + "\n")
        except Exception as e:
            print(f"Erro ao salvar log: {e}")

        # --- Scroll to bottom using the scroll bar ---
        v_scrollbar = self.message_box.verticalScrollBar()
        # Dá um pequeno tempo para a UI processar o append antes de rolar
        # Usar QTimer.singleShot para evitar bloqueio e garantir que a rolagem aconteça após a atualização
        if v_scrollbar is not None:
            QTimer.singleShot(10, lambda: v_scrollbar.setValue(v_scrollbar.maximum()))

        # Processa eventos para tentar manter a UI responsiva (usar com moderação)
        # QApplication.processEvents() # Removido daqui, pode causar lentidão se chamado muito rápido


    def on_transcription_finished(self):
        """Chamado quando a thread de trabalho termina."""
        self.running = False
        self.transcribe_btn.setEnabled(True)
        self.update_ui_visibility() # Restaura texto/tooltip do botão
        print("Thread de trabalho finalizada.")

    def on_transcription_error(self, error_message):
        """Chamado se a thread emitir um erro específico."""
        self.update_message_box(f"🛑 ERRO FATAL: {error_message}")
        self.on_transcription_finished() # Reseta a UI mesmo em erro

    def check_transcription_status(self):
        """Verifica periodicamente se a thread ainda está ativa."""
        # Não mais estritamente necessário com signals, mas pode ser mantido para debug.
        pass

def get_log_dir():
    """Retorna o diretório onde os logs serão salvos."""
    log_dir = os.path.join(get_download_dir(), "Kiwiscribe_Logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def cleanup_old_logs(log_dir, max_logs=10):
    """Mantém apenas os logs mais recentes, removendo os mais antigos."""
    try:
        if not os.path.exists(log_dir):
            return
            
        # Lista todos os arquivos de log
        log_files = [f for f in os.listdir(log_dir) if f.startswith('kiwiscribe_log_') and f.endswith('.txt')]
        
        # Se houver mais logs que o máximo permitido
        if len(log_files) > max_logs:
            # Ordena por data (mais recentes primeiro)
            log_files.sort(reverse=True)
            
            # Remove os logs mais antigos
            for old_log in log_files[max_logs:]:
                try:
                    os.remove(os.path.join(log_dir, old_log))
                except Exception as e:
                    print(f"Erro ao remover log antigo {old_log}: {e}")
    except Exception as e:
        print(f"Erro ao limpar logs antigos: {e}")

# --- Bloco Principal ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        app.setStyle("Fusion")
    except Exception as e:
        print(f"Não foi possível aplicar estilo: {e}")

    # Limpa logs antigos antes de iniciar
    log_dir = get_log_dir()
    cleanup_old_logs(log_dir)

    window = TranscriptionWindow()
    window.show()
    sys.exit(app.exec())
