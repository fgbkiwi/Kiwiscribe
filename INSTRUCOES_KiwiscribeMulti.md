# KiwiscribeMulti.py - Instruções de Uso

## Visão Geral

O **KiwiscribeMulti.py** é um script especializado para transcrição de audiências
trabalhistas gravadas com **4 canais de áudio** usando o gravador
**Sound Devices MixPre-6M**.

## Mapeamento de Canais

O script mapeia automaticamente os canais de áudio para os papéis judiciais:

- **Canal 1**: Juiz
- **Canal 2**: Advogado do Reclamante  
- **Canal 3**: Advogado do Reclamado
- **Canal 4**: Depoente (Reclamante → Reclamado → Testemunhas, conforme
  sequência da ata)

## Requisitos

### Software

- Python 3.13 com ambiente virtual ativado
- Dependências instaladas (PyQt6, assemblyai, etc.)
- ffprobe (para validação de canais de áudio)

### Hardware

- Arquivo WAV multicanal com **4 ou mais canais** (ex: MixPre-6M com 8
  canais)
- Arquivo da ata em PDF ou TXT

### APIs

- **AssemblyAI**: Obrigatória para transcrição (pode usar chave padrão)
- **Claude/OpenAI/Gemini**: Opcional para pós-processamento

## Como Usar

### 1. Executar o Script

```bash
# Ativar ambiente virtual
.\venv_win\Scripts\activate

# Executar o script
python KiwiscribeMulti.py
```

### 2. Configurar Arquivos

1. **Áudio WAV (4 canais)**: Selecione o arquivo WAV multicanal
2. **Ata**: Selecione o arquivo PDF ou TXT da ata da audiência

### 3. Configurar APIs

- **AssemblyAI Key**: Obrigatória (pode usar a chave padrão)
- **API Key do LLM**: Escolha um serviço (Claude, GPT-4o ou Gemini) e insira a
  chave

### 4. Iniciar Processo

Clique em **"🎙️ Iniciar Transcrição Multicanal"**

## Processo de Transcrição

### Validações Automáticas

1. ✅ Verifica se o arquivo é WAV
2. ✅ Valida que tem pelo menos 4 canais (aceita 8 canais do MixPre-6M)
3. ✅ Extrai informações da ata
4. ✅ Identifica sequência de depoentes

### Transcrição

- Usa AssemblyAI com parâmetro `multichannel: True`
- Mapeia automaticamente canais 0-2 para papéis fixos
- Identifica depoentes no canal 3 baseado na sequência da ata

### Saída

Arquivo de texto com formato:

```text
[HH:MM:SS --> HH:MM:SS] Juiz: texto
[HH:MM:SS --> HH:MM:SS] Advogado do Reclamante: texto
[HH:MM:SS --> HH:MM:SS] Advogado do Reclamado: texto
[HH:MM:SS --> HH:MM:SS] Reclamante: texto
[HH:MM:SS --> HH:MM:SS] 1ª Testemunha do Reclamante: texto
```

## Identificação de Depoentes

O script identifica automaticamente a sequência de depoentes na ata:

1. **Depoimento do Reclamante** (se gravado)
2. **Depoimento do Reclamado** (se gravado)
3. **Testemunhas do Reclamante** (1ª, 2ª, etc.)
4. **Testemunhas do Reclamado** (1ª, 2ª, etc.)

### Lógica de Mudança de Depoente

- Detecta pausas longas (>30 segundos) no canal 3
- Avança automaticamente para o próximo depoente da lista
- Avisa se número de mudanças ≠ número de depoentes na ata

## Diferenças do Kiwiscribe.py Original

| Aspecto | Kiwiscribe.py | KiwiscribeMulti.py |
| --- | --- | --- |
| **Serviços de Transcrição** | AssemblyAI, OpenAI, Gemini | Apenas AssemblyAI |
| **Identificação de Falantes** | Speaker diarization | Por canais de áudio |
| **Número de Canais** | Qualquer | 4+ canais (aceita 8 do MixPre-6M) |
| **Mapeamento** | Automático/Manual | Fixo por canal |
| **Depoentes** | Identificação genérica | Sequencial baseada na ata |

## Solução de Problemas

### Erro: "Arquivo não tem 4 canais"

- Verifique se o arquivo WAV foi gravado com pelo menos 4 canais
- Arquivos do MixPre-6M com 8 canais são aceitos (apenas os primeiros 4 são
  processados)
- Use ffprobe para verificar:

  ```bash
  ffprobe -v error -select_streams a:0 -show_entries stream=channels arquivo.wav
  ```

### Erro: "Nenhum depoente identificado"

- Verifique se a ata contém as seções de depoimentos
- Certifique-se de que os depoimentos estão marcados como "gravado"

### Erro: "API Key não fornecida"

- Insira a chave da AssemblyAI (obrigatória)
- Para pós-processamento, insira a chave do LLM escolhido

## Arquivos Gerados

- **Transcrição**: `{nome_audio}_transcricao_multicanal_{timestamp}.txt`
- **Localização**: Pasta de Downloads do usuário
- **Formato**: Texto com timestamps e identificação por canal

## Lembrete de Ambiente por Plataforma

- No Windows, este projeto usa `venv_win` e o script `update_deps_win.bat` para atualização de dependências.
- Ao trabalhar no Linux, crie um ambiente virtual separado (por exemplo, `.venv_linux`) e um script de atualização próprio (por exemplo, `update_deps_linux.sh`).
- Não reutilize o mesmo ambiente virtual entre Windows e Linux.

## Suporte

Para dúvidas ou problemas:

1. Verifique os logs na caixa "Log de Execução"
2. Confirme que o arquivo WAV tem exatamente 4 canais
3. Verifique se a ata contém informações de depoimentos
4. Teste com a chave padrão da AssemblyAI primeiro
