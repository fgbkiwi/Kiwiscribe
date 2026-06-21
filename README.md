# Kiwiscribe

Kiwiscribe é um conjunto de ferramentas em Python para transcrição e pós-processamento de gravações de audiências judiciais trabalhistas, com foco em fluxo jurídico (audiências e atas), interface gráfica em PyQt6 e integrações com diferentes provedores de IA.

## Visão Geral

O repositório contém três aplicações principais:

- ‘Kiwiscribe.py’: app GUI principal para transcrição e pós-processamento.
- ‘KiwiscribeMulti.py’: variante para fluxo de 4 canais de áudio.
- ‘KiwiscribeWord.py’: utilitário para gerar/ajustar documentos Word a partir de transcrições e metadados.

Também inclui automações para:

- build de executável com PyInstaller;
- build de instalador Windows com pynsist/NSIS;
- verificação e atualização segura de dependências;
- teste de conectividade com APIs.

## Principais Recursos

- Interface gráfica com PyQt6.
- Transcrição com múltiplos provedores/modelos (AssemblyAI, OpenAI, Gemini, Soniox).
- Pós-processamento com Claude, OpenAI ou Gemini.
- Persistência local de chaves em arquivo JSON de configuração do usuário.
- Extração de metadados de PDF (ata) para enriquecer o fluxo de trabalho.
- Build distribuível como ‘.exe’ único (PyInstaller) ou instalador ‘.exe’ (pynsist + NSIS).

## Requisitos

- Python 3.13.x (recomendado 3.13.13).
- Windows 10/11 para build de instalador.
- Ambiente virtual local (‘venv_win’ no Windows).
- Internet para chamadas de API e download de dependências.
- Internet para chamadas de API e download de dependências.

## Estrutura de Arquivos Importantes

- ‘Kiwiscribe.py’: aplicação principal.
- ‘KiwiscribeMulti.py’: fluxo multicanal.
- ‘KiwiscribeWord.py’: processamento e geração de ‘.docx’.
- ‘requirements_build.txt’: dependências de runtime/build de exe.
- ‘requirements_installer.txt’: dependências para empacotamento do instalador.
- ‘dependency_manager.py’: gerenciador de conflitos e atualizações seguras.
- ‘build_exe.bat’: build do executavel PyInstaller.
- ‘build_installer.bat’: build do instalador Windows com pynsist.
- ‘kiwiscribe_installer.cfg’: configuração do instalador.
- ‘kiwiscribe_launcher.py’: launcher para o instalador.
- ‘CHANGELOG.md’: histórico de versões.
- ‘BUILD_INSTRUCTIONS.md’: guia de build detalhado.

## Instalação e Setup

### 1. Criar/ativar ambiente virtual (Windows)

Se já existir ‘venv_win’, apenas ative:

```bat
venv_win\Scripts\activate
```

Ou use o atalho:

```bat
activate_env.bat
```

### 2. Instalar dependências

```bat
python -m pip install --upgrade pip
python -m pip install -r requirements_build.txt
```

### 3. Configurar chaves de API

As chaves são salvas em:

- ‘%USERPROFILE%\.transcription_config.json’

A app principal permite preencher chaves via interface e salva automaticamente.

## Como Executar

### Aplicacao principal

```bat
python Kiwiscribe.py
```

### Variação multi-canal

```bat
python KiwiscribeMulti.py
```

### Utilitário Word

```bat
python KiwiscribeWord.py
```

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

- ativa o ‘venv_win’;
- garante pynsist instalado;
- baixa wheels para ‘installer_wheels’;
- executa ‘python -m nsist kiwiscribe_installer.cfg’;
- gera instalador em ‘build\nsis’.

Saída esperada:

- ‘build\nsis\Kiwiscribe-1.0.0-win64.exe’

## Versionamento

O projeto adotou **Semantic Versioning (SemVer)**.

Formato:

- ‘MAJOR.MINOR.PATCH’

Regras práticas:

- **MAJOR**: quebra de compatibilidade.
- **MINOR**: nova funcionalidade retrocompatível.
- **PATCH**: correção sem quebra de compatibilidade.

Estado atual:

- Versão da app: ‘1.0.0’ (em ‘Kiwiscribe.py’).
- Changelog inicial: ‘CHANGELOG.md’.
- Nome do instalador: ‘Kiwiscribe-1.0.0-win64.exe’.

Sugestão de próxima evolução:

- ‘1.0.1’ para hotfix;
- ‘1.1.0’ para novas features sem quebra;
- ‘2.0.0’ para mudanças breaking.

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
python -m pip install -U pynsist
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
- Ao mudar versão, sincronize:
  - ‘APP_VERSION’ em ‘Kiwiscribe.py’;
  - ‘version’ e ‘installer_name’ em ‘kiwiscribe_installer.cfg’.
- Antes de commit/release:
  - rode ‘check_deps.bat’;
  - teste execucao local (‘python Kiwiscribe.py’);
  - valide build (‘build_exe.bat’ e/ou ‘build_installer.bat’).

## Roadmap Sugerido

- Automatizar bump de versão em um único comando.
- Criar pipeline CI para build de ‘.exe’ e instalador.
- Publicar artefatos por release no GitHub.
- Adicionar testes automatizados para fluxos críticos.

## Avisos

- Chaves de API são dados sensíveis: não versionar arquivos com credenciais.
- O executável/instalador pode ficar grande devido ao conjunto de dependências de IA.

---

Se quiser, posso gerar em seguida um script de release (ex.: ‘release.bat’) para atualizar versão em todos os pontos automaticamente e reduzir erros manuais de SemVer.


