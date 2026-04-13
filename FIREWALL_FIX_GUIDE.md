# Guia de Resolução de Problemas de Conexão (Firewall/SSL) - Kiwiscribe

O erro abaixo indica que o Python conseguiu iniciar a conexão com o Google Gemini,
mas a negociação de segurança (SSL Handshake) foi bloqueada ou interrompida.

```text
httpx.ConnectTimeout: _ssl.c:1015:
The handshake operation timed out
```

Como a OpenAI funciona normalmente, o problema é específico com os domínios ou
configurações de rede relacionados ao Google.

## Passo 1: Verificar o Windows Defender Firewall (Método Rápido via PowerShell)

Execute este comando no **PowerShell (como Administrador)** para ver se há regras
bloqueando o Python:

```powershell
Get-NetFirewallRule -DisplayName "*python*" |
    Format-Table DisplayName, Direction, Action, Enabled
```

- **O que procurar:** Regras com `Action: Block` e `Enabled: True`.
- **Como corrigir:** Se encontrar regras de bloqueio para o Python, você pode
    desativá-las ou criar uma regra de permissão.

Para **permitir o Python automaticamente**, você pode rodar (subistitua o caminho
se seu python estiver em outro lugar; o comando abaixo usa o do ambiente virtual
atual):

```powershell
$basePath = Join-Path $env:USERPROFILE `
    "OneDrive - NetJus\Dev\PythonApps"
$pythonPath = Join-Path $basePath `
    "Kiwiscribe\venv\Scripts\python.exe"

New-NetFirewallRule -DisplayName "Python Kiwiscribe Allow Outbound" `
    -Direction Outbound `
    -Program $pythonPath `
    -Action Allow
```

## Passo 2: Verificar Antivírus com "Inspeção HTTPS/SSL"

Softwares como **Kaspersky, Bitdefender, ESET ou Avast** interceptam tráfego SSL
para escanear vírus. Eles tentam substituir o certificado SSL temporariamente,
o que o Python e a biblioteca do Google rejeitam por segurança.

1. Abra seu Antivírus.
2. Procure configurações de **Web Shield**, **Network Protection** ou
    **SSL Scanning**.
3. Adicione uma exceção para o executável do Python (ajuste o caminho):

    ```text
    C:\caminho\para\Kiwiscribe\venv\Scripts\python.exe
    ```

4. Ou desative temporariamente a verificação de HTTPS/SSL (não a proteção de arquivos)
    para testar.

## Passo 3: VPN ou Proxy Corporativo

Se você estiver usando:

- **VPN Corporativa:** Desconecte para testar.
- **Zscaler / Netskope:** Esses agentes de segurança de rede frequentemente
    bloqueiam APIs não reconhecidas.

## Passo 4: Teste de Conexão Simples (Sem Python)

Tente abrir este link diretamente no navegador
para ver se carrega:
[https://generativelanguage.googleapis.com](https://generativelanguage.googleapis.com)

- Se carregar (mesmo que dê erro 404 de página não encontrada do Google), sua rede
    está OK e o bloqueio é apenas no aplicativo Python.
- Se der timeout ou erro de conexão no navegador, o bloqueio é na rede inteira de sua
    máquina para esse domínio.
