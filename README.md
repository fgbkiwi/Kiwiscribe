# Kiwiscribe

Kiwiscribe é um conjunto de ferramentas em Python para transcrição e pós-processamento de gravações de audiências judiciais trabalhistas, com foco em fluxo jurídico (audiências e atas), interface gráfica em PyQt6 e integrações com diferentes provedores de IA.

## Visão Geral

O repositório contém duas aplicações principais:

- ‘Kiwiscribe.py’: app GUI principal para transcrição, pós-processamento e geração de documentos Word (.docx).
- ‘KiwiscribeWord.py’: utilitário opcional/legado para execução isolada da geração de documento Word.

Também inclui automações para:

- build de executável com PyInstaller;
- build de instalador Windows com pynsist/NSIS;
- build de instalador Debian (`.deb`) para Pop!_OS / Ubuntu;
- verificação automática de novas versões no startup (GitHub Releases);
- verificação e atualização segura de dependências;
- teste de conectividade com APIs.

## Principais Recursos

- Interface gráfica com PyQt6.
- Transcrição com múltiplos provedores/modelos (AssemblyAI, OpenAI, Gemini, OpenRouter, Soniox).
- Pós-processamento com Claude, OpenAI, Gemini ou OpenRouter.
- Geração opcional de documento Word (.docx) com transcrição organizada por títulos na própria UI.
- Modo dedicado “Apenas Gerar DOCX (Txt Local)” para criar o documento sem transcrever áudio.
- Persistência local de chaves em arquivo JSON de configuração do usuário.
- Extração de metadados de PDF (ata) para enriquecer o fluxo de trabalho.
- Build distribuível como ‘.exe’ único (PyInstaller), instalador Windows (pynsist + NSIS) ou pacote ‘.deb’ (Pop!_OS / Ubuntu).
- Verificação automática de atualizações no startup (no máximo 1x por dia).

## Requisitos

- Python 3.13.x (recomendado 3.13.13).
- Windows 10/11 para build do instalador Windows; Linux (Pop!_OS / Ubuntu) para build do ‘.deb’.
- Ambiente virtual local (‘.venv’ no Windows; ‘.venv’ ou ‘.venv_linux’ no Linux).
- Internet para chamadas de API e download de dependências.

## Estrutura de Arquivos Importantes

- ‘Kiwiscribe.py’: aplicação principal.
- ‘KiwiscribeWord.py’: processamento e geração de ‘.docx’.
- ‘kiwiscribe_updates.py’: verificação/download/instalação de atualizações via GitHub Releases.
- ‘requirements_build.txt’: dependências de runtime/build de exe.
- ‘requirements_installer.txt’: dependências para empacotamento do instalador.
- ‘dependency_manager.py’: gerenciador de conflitos e atualizações seguras.
- ‘build_exe.bat’: build do executavel PyInstaller.
- ‘build_installer.bat’: build do instalador Windows com pynsist.
- ‘build_kiwiscribe_deb.sh’: build do instalador Debian para Pop!_OS / Ubuntu.
- ‘packaging/linux/’: launcher, desktop entry e scripts do pacote ‘.deb’.
- ‘kiwiscribe_installer.cfg’: configuração do instalador Windows.
- ‘kiwiscribe_launcher.py’: launcher para o instalador.
- ‘CHANGELOG.md’: histórico de versões.

## Instalação e Setup

### 1. Criar/ativar ambiente virtual (Windows)

Criar o ambiente (com ‘uv’):

```bat
uv venv .venv --python 3.13
```

Se já existir ‘.venv’, apenas ative:

```bat
.venv\Scripts\activate
```

Ou use o atalho:

```bat
activate_env.bat
```

### 2. Instalar dependências

```bat
uv pip install -r requirements_build.txt
```

Alternativa com pip:

```bat
python -m pip install --upgrade pip
python -m pip install -r requirements_build.txt
```

### 3. Configurar chaves de API

As chaves são salvas em:

- ‘%USERPROFILE%\.transcription_config.json’

A app principal permite preencher chaves via interface e salva automaticamente.

Chave adicional suportada:

- OpenRouter (usada para transcrição e/ou pós-processamento quando o provedor OpenRouter estiver selecionado).

## Como Executar

### Aplicacao principal

```bat
python Kiwiscribe.py
```

Na interface, a seção 5 permite:

- gerar DOCX ao final do fluxo normal (transcrição/pós-processamento);
- gerar apenas DOCX a partir de um TXT local, sem transcrição.

O DOCX é salvo na mesma pasta do TXT utilizado como entrada/final.

OpenRouter na prática:

- os combos de modelo são carregados dinamicamente da API de modelos do OpenRouter;
- o combo de transcrição mostra apenas modelos com entrada de áudio e saída de texto;
- o combo de pós-processamento mostra apenas modelos com entrada de texto e saída de texto;
- modelos incompatíveis (por exemplo, apenas imagem/vídeo) não são exibidos nesses combos.

#### Transcrição via OpenRouter: peculiaridade da API (JSON/base64)

A transcrição com OpenRouter **não** usa o endpoint dedicado `/audio/transcriptions`
(Whisper). Esse endpoint tinha duas limitações incompatíveis com o fluxo jurídico:

1. devolvia apenas texto corrido, sem timestamps nem separação de interlocutores;
2. expunha somente modelos STT dedicados (Whisper / GPT-4o-transcribe), deixando o
   menu de seleção artificialmente restrito.

Em vez disso, a transcrição agora usa o endpoint `/chat/completions`, enviando o áudio
como um bloco `input_audio` codificado em **base64** dentro de um **corpo JSON** — e
não como `multipart/form-data`. Essa é a peculiaridade central da API do OpenRouter: o
upload de arquivo binário multipart é rejeitado (`invalid content-type`); o áudio
precisa ir embutido no JSON. A estrutura enviada é:

```json
{
  "model": "google/gemini-2.5-flash",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "<prompt de transcrição com diarização>" },
        { "type": "input_audio", "input_audio": { "data": "<base64>", "format": "mp3" } }
      ]
    }
  ]
}
```

Consequências práticas dessa abordagem (mesma estratégia já usada na transcrição via
Gemini):

- a saída vem em **múltiplas linhas**, com timestamps e interlocutores rotulados
  (`Speaker 1`, `Speaker 2`, ...), viabilizando o pós-processamento que mapeia os
  falantes para os nomes reais extraídos da ata;
- o menu de modelos de transcrição volta a listar **todos os modelos com entrada de
  áudio** (Gemini, GPT-4o Audio etc.), não apenas Whisper;
- como o áudio vai embutido em base64 (sem upload prévio), prefira modelos **Gemini**
  para áudios longos, pois lidam melhor com contexto/áudio extenso; o timeout das
  requisições foi ampliado para acomodar a latência maior de LLMs de áudio.

### Utilitário Word

```bat
python KiwiscribeWord.py
```

Observação: a funcionalidade de geração DOCX já está incorporada ao fluxo principal do Kiwiscribe.py (seção 5 da interface e modo “Apenas Gerar DOCX”).

## Build de Executável (PyInstaller)

Método recomendado:

```bat
build_exe.bat
```

Saida esperada:

- ‘Kiwiscribe.exe’ na raiz do projeto.

## Build de Instalador Windows (pynsist)

Método recomendado:

```bat
build_installer.bat
```

Esse fluxo:

- ativa o ambiente virtual local (‘.venv’, ‘venv_win’ ou equivalentes);
- incrementa a versão do app automaticamente (padrão: ‘patch’) e sincroniza ‘Kiwiscribe.py’ e ‘kiwiscribe_installer.cfg’;
- garante pynsist instalado;
- baixa wheels para ‘installer_wheels’;
- executa ‘python -m nsist kiwiscribe_installer.cfg’;
- gera instalador em ‘build\nsis’;
- faz commit/push **apenas** do bump de versão (‘Kiwiscribe.py’ e ‘kiwiscribe_installer.cfg’);
- publica o instalador como asset na release GitHub ‘v\<versão\>’ (via ‘gh’).

Pré-requisitos para a publicação no GitHub:

- [GitHub CLI](https://cli.github.com/) instalado (‘gh’);
- autenticação: ‘gh auth login’;
- permissão de push/release no repositório remoto.

Observação: outras modificações locais pendentes **não** são commitadas automaticamente — só os arquivos de versão.

Para escolher o tipo de incremento:

```bat
build_installer.bat            :: 1.0.0 -> 1.0.1 (patch, padrão)
build_installer.bat minor      :: 1.0.0 -> 1.1.0
build_installer.bat major      :: 1.0.0 -> 2.0.0
build_installer.bat nobump     :: mantém a versão atual (sem incrementar)
```

Saída esperada:

- ‘build\nsis\Kiwiscribe-<versão>-win64.exe’
- Release em ‘https://github.com/fgbkiwi/Kiwiscribe/releases’ com o instalador anexado (tag ‘v\<versão\>’)

## Build de Instalador Linux (Pop!_OS / Ubuntu)

Método recomendado (equivalente Linux do ‘build_installer.bat’):

```bash
./build_kiwiscribe_deb.sh --no-bump --no-publish   # gera + instala localmente
./build_kiwiscribe_deb.sh                          # bump patch + gera + publica + instala
./build_kiwiscribe_deb.sh minor                    # bump minor + publica + instala
./build_kiwiscribe_deb.sh --no-bump                # empacota a versão atual, publica e instala
./build_kiwiscribe_deb.sh --no-install             # só gera/publica, sem instalar nesta máquina
```

Esse fluxo:

- prepara um CPython 3.13 embutido via ‘uv’ (o Python do sistema no Ubuntu/Pop 24.04 é 3.12);
- instala as dependências de ‘requirements_installer.txt’ no runtime empacotado;
- monta o pacote em ‘/opt/kiwiscribe’ com atalho em ‘/usr/bin/kiwiscribe’ e entrada no menu;
- gera ‘build/deb/Kiwiscribe_<versão>_<arch>.deb’;
- **instala o ‘.deb’ nesta máquina** (pede senha via ‘pkexec’/‘sudo’) para o atalho aparecer no App Library do Pop!_OS;
- opcionalmente anexa o ‘.deb’ à Release GitHub ‘v\<versão\>’ (ou cria a Release se ainda não existir).

Pré-requisitos:

- ‘uv’ instalado ([docs.astral.sh/uv](https://docs.astral.sh/uv/));
- ‘dpkg-deb’ (pacote ‘dpkg’);
- para publicar: GitHub CLI (‘gh auth login’).

Instalação no Pop!_OS / Ubuntu:

```bash
sudo apt install ./build/deb/Kiwiscribe_<versão>_amd64.deb
```

Depois abra pelo menu de aplicativos ou rode ‘kiwiscribe’.

## Atualizações automáticas

No startup, o Kiwiscribe consulta a última Release em GitHub (no máximo 1x por dia). Se houver versão mais nova:

- no Windows, oferece baixar e executar o instalador ‘.exe’;
- no Linux, baixa o ‘.deb’ e instala com ‘pkexec’ + ‘apt’ (substitui o pacote do menu de aplicativos).

Estado da verificação: ‘~/.local/share/Kiwiscribe/update_check.json’ (Linux) ou ‘%LOCALAPPDATA%\Kiwiscribe\update_check.json’ (Windows).

## Versionamento

O projeto adotou **Semantic Versioning (SemVer)**.

Formato:

- ‘MAJOR.MINOR.PATCH’

Regras práticas:

- **MAJOR**: quebra de compatibilidade.
- **MINOR**: nova funcionalidade retrocompatível.
- **PATCH**: correção sem quebra de compatibilidade.

Bump automático:

- ‘APP_VERSION’ em ‘Kiwiscribe.py’ é a fonte única da versão.
- ‘build_installer.bat’ incrementa a versão a cada build (padrão ‘patch’) via ‘bump_version.py’,
  sincronizando ‘Kiwiscribe.py’ e ‘kiwiscribe_installer.cfg’.
- Use ‘build_installer.bat minor’ ou ‘build_installer.bat major’ para os demais incrementos.
- Use ‘build_installer.bat nobump’ para gerar o instalador sem alterar a versão.
- Como o bump ocorre a cada execução (exceto com ‘nobump’), re-rodar o build repetidamente continua incrementando o ‘patch’.

Estado atual:

- Versão da app: ‘1.0.0’ (em ‘Kiwiscribe.py’).
- Changelog inicial: ‘CHANGELOG.md’.
- Nome do instalador: ‘Kiwiscribe-<versão>-win64.exe’.

## Verificação e Atualização de Dependências

### Checar conflitos

```bat
check_deps.bat
```

ou

```bat
python dependency_manager.py check
```

### Atualizar com segurança

```bat
update_deps_win.bat
```

ou

```bat
python dependency_manager.py update
```

### Linux (fluxo separado)

```bash
./update_deps_linux.sh
```

## Diagnóstico de Conectividade

Para testar conectividade com OpenAI e Gemini:

```bat
python test_connectivity.py
```

## Troubleshooting

### 1. ‘No module named nsist’

- Instale/atualize pynsist no ambiente ativo:

```bat
uv pip install -U pynsist
```

Observação: o pacote chama ‘pynsist’, mas o módulo/entry point usado no build é ‘nsist’.

### 2. ‘makensis’ não encontrado

- Instale NSIS e confirme que ‘makensis’ está disponível no sistema.

### 3. Falha no build do instalador por dependência

- Limpe artefatos:

```bat
rmdir /s /q installer_wheels
rmdir /s /q build\nsis
```

- Rode novamente ‘build_installer.bat’.

### 4. APIs não respondem

- Revise chaves no arquivo ‘%USERPROFILE%\.transcription_config.json’.
- Execute ‘python test_connectivity.py’.
- Consulte ‘FIREWALL_FIX_GUIDE.md’ se houver bloqueio de rede/corporativo.

## Boas Práticas de Contribuição

- Mantenha ‘requirements_build.txt’ e ‘requirements_installer.txt’ consistentes.
- Atualize ‘CHANGELOG.md’ a cada release.
- A versão é incrementada automaticamente pelo ‘build_installer.bat’ (via ‘bump_version.py’),
  que sincroniza ‘APP_VERSION’ em ‘Kiwiscribe.py’ e ‘version’ em ‘kiwiscribe_installer.cfg’.
  Não é mais necessário editar a versão manualmente.
- Antes de commit/release:
  - rode ‘check_deps.bat’;
  - teste execucao local (‘python Kiwiscribe.py’);
  - valide build (‘build_exe.bat’ e/ou ‘build_installer.bat’).

## Roadmap Sugerido

- Criar pipeline CI para build de ‘.exe’ e instalador.
- Adicionar testes automatizados para fluxos críticos.

## Avisos

- Chaves de API são dados sensíveis: não versionar arquivos com credenciais.
- O executável/instalador pode ficar grande devido ao conjunto de dependências de IA.

