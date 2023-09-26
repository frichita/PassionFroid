@echo off
echo Lancement de l'application...

rem Activez l'environnement virtuel Python
call venv\Scripts\activate

rem Installez les dépendances Python
pip install -r requirements.txt

rem Attendez un peu avant de passer à la suite (ajustez la durée si nécessaire)
timeout /t 5

rem Naviguez vers le dossier du frontend React
cd client

rem Lancer le frontend React
start "Frontend React" npm start &

rem Lancer le frontend React
cd ../

rem Attendez un peu avant de passer à la suite (ajustez la durée si nécessaire)
timeout /t 10

rem Lancer le backend Python
start "Backend Python" python server.py

rem Attendre la fin de l'exécution du frontend (ajustez la durée si nécessaire)
timeout /t 10

echo L'application est lancée.

rem Attendez indéfiniment pour garder la fenêtre de commande ouverte
pause
