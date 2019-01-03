::
:: Python configuration
::

set python_installer_extension=%YCM_PYTHON_INSTALLER_URL:~-3%

if "%python_installer_extension%" == "exe" (
  curl %YCM_PYTHON_INSTALLER_URL% -o C:\python-installer.exe
  C:\python-installer.exe /quiet TargetDir=C:\Python
) else (
  curl %YCM_PYTHON_INSTALLER_URL% -o C:\python-installer.msi
  msiexec /i C:\python-installer.msi TARGETDIR=C:\Python /qn
)

C:\Python\Scripts\pip install -r test_requirements.txt --disable-pip-version-check --no-warn-script-location

:: Enable coverage for Python subprocesses. See:
:: http://coverage.readthedocs.io/en/latest/subprocess.html
C:\Python\python -c "with open('C:\Python\Lib\site-packages\sitecustomize.py', 'w') as f: f.write('import coverage\ncoverage.process_startup()')"

::
:: Go configuration
::

curl https://dl.google.com/go/go1.12.4.windows-amd64.msi -o C:\go-installer.msi
msiexec /i C:\go-installer.msi TARGETDIR=C:\Go /qn

::
:: PHP Configuration.
::
set PHP_VERSION=7.3.0
set PHP_VERSION_ZIP=php-%PHP_VERSION%-Win32-VC15-x86.zip
curl https://windows.php.net/downloads/releases/%PHP_VERSION_ZIP% -o C:\%PHP_VERSION_ZIP%
7z x C:\%PHP_VERSION_ZIP% -oC:\PHP
set PATH=C:\PHP;%PATH%

curl https://getcomposer.org/Composer-Setup.exe -o C:\Composer-Setup.exe
C:\Composer-Setup.exe /silent /norestart
set PATH=C:\ProgramData\ComposerSetup\bin;%PATH%;%USERPROFILE%\AppData\Roaming\Composer\vendor\bin

:: Print PHP Info
php -i
composer --version
