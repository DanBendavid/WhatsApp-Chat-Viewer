# WhatsApp Chat Viewer

Visualiseur local pour un export WhatsApp (`_chat.txt`) avec timeline, médias et impression.

![Aperçu](ViewerImage.jpg)

## Démarrage rapide

1. Ouvrir `whatsapp-viewerV2.html`.
1. Le fichier `_chat.txt` est chargé automatiquement si la page est servie par un serveur local.
1. Si le chargement auto échoue (blocage `file://`), utilisez le bouton **Choisir _chat.txt**.

## Lancer un serveur local (recommandé)

Option simple avec Python :

```powershell
python -m http.server 8000
```

Puis ouvrir `http://localhost:8000/whatsapp-viewerV2.html`.

## Impression

- Le header/footer imprimés sont personnalisés (titre + pagination).
- Pour supprimer les en‑têtes/pieds de page du navigateur, désactivez l’option correspondante dans le dialogue d’impression.

## Script de correction `_chat.txt`

Le script `correct_chat_local.py` corrige la grammaire/orthographe via l’API OpenAI.

Variables d’environnement utiles :

- `OPENAI_API_KEY` (obligatoire)
- `OPENAI_API_BASE` (optionnel, défaut `https://api.openai.com/v1`)
- `OPENAI_MODEL` (optionnel, défaut `gpt-4o-mini`)
- `LOCAL_OPENAI_MAX_CHARS` (optionnel, défaut `30000`)
- `LOCAL_OPENAI_MERGE_ONLY` (optionnel, `1/true/yes` pour ne faire que la fusion)

Exécution :

```powershell
python correct_chat_local.py
```

Les fichiers générés sont ignorés par `.gitignore`.
