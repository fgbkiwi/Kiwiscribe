# Changelog

## Unreleased

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