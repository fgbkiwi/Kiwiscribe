# Changelog

## Unreleased

- Correção: o pós-processamento deixava de ser executado em re-execuções (especialmente
  no modo "Apenas Pós-processar") porque a escolha do pós-processador era lida dos
  `QRadioButton` dentro do thread de trabalho, retornando estado obsoleto. A seleção
  passa a ser capturada no thread da GUI em `start_transcription` e repassada ao
  `perform_transcription_workflow` como parâmetro.
- Build: `build_installer.bat` passa a incrementar automaticamente a versão do app antes
  de cada build, seguindo versionamento semântico (padrão: `patch`). Use
  `build_installer.bat minor` ou `build_installer.bat major` para os demais incrementos.
- Adicionado `bump_version.py`: fonte única da versão é `APP_VERSION` em `Kiwiscribe.py`;
  o script incrementa e sincroniza a versão em `Kiwiscribe.py` e `kiwiscribe_installer.cfg`
  (a versão do `[Python]` no `.cfg` não é alterada).

- Segurança: removida a API Key da AssemblyAI embutida no código-fonte; a chave passa a
  vir exclusivamente do arquivo `.transcription_config.json` (campo `assembly_ai`) ou da
  interface. Sem chave configurada, a transcrição é abortada com mensagem clara.
- Instalador: incluídos `KiwiscribeWord.py` e o template de degravação no pacote pynsist
  (antes ausentes, o que desabilitava a geração de DOCX na versão instalada).
- Template de degravação renomeado para `Degravacao_script.docx` (nome ASCII) para evitar
  falha de codificação do NSIS; `KiwiscribeWord.py` aceita o nome antigo como fallback.
- `build_installer.bat`: passa a verificar se o `.exe` foi realmente gerado (o pynsist
  retornava 0 mesmo quando o makensis falhava) e propaga código de saída não-zero em falhas.

- Corrigida a transcrição via OpenRouter: substituído o endpoint `/audio/transcriptions`
  (multipart, rejeitado com `invalid content-type`) pelo endpoint `/chat/completions`
  com áudio embutido em base64 no corpo JSON (bloco `input_audio`).
- A saída da transcrição via OpenRouter passou a ser multilinha, com timestamps e
  interlocutores rotulados, viabilizando o pós-processamento com identificação de falantes.
- Ampliado o filtro de modelos de transcrição do OpenRouter para listar todos os modelos
  com entrada de áudio (Gemini, GPT-4o Audio etc.), não apenas Whisper.
- Modelos padrão de transcrição do OpenRouter atualizados para Gemini 2.5 Flash/Pro e
  GPT-4o Audio.

## 1.0.0

- First semantic release of Kiwiscribe.
- Added a pynsist-based Windows installer workflow.
- Standardized the application version to `1.0.0`.