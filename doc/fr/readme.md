# Gestionnaire d'historique du presse-papiers

Un gestionnaire d'historique du presse-papiers pour NVDA inspiré de Ditto.

Garde une trace de tout ce que vous copiez — texte, fichiers, liens et e-mails — avec une surveillance instantanée du presse-papiers basée sur les événements.

## Fonctionnalités

* **Surveillance instantanée du presse-papiers** utilisant l'écouteur de presse-papiers Windows (basé sur les événements, sans interrogation périodique).
* **Support des fichiers** : Les fichiers copiés dans l'Explorateur apparaissent dans l'historique et sont collés comme de vrais fichiers (format CF_HDROP).
* **Regroupement automatique** : Les entrées sont automatiquement classées en Fichiers et dossiers, Liens ou E-mails.
* **Recherche et filtrage** : Recherche en texte intégral et filtre par groupe dans la boîte de dialogue.
* **Épingler les entrées importantes** pour qu'elles ne soient jamais supprimées lorsque la limite est atteinte.
* **Sélection multiple et collage** : Sélectionnez plusieurs entrées avec Ctrl+Espace et collez dans l'ordre de sélection.
* **Ajouter au presse-papiers** : Ajoutez le texte sélectionné au contenu actuel du presse-papiers.
* **Réordonner les entrées** : Déplacez les entrées vers le haut/bas avec Shift+Flèches, ou vers le haut/bas via le menu contextuel.
* **Sauvegarder les entrées** : Enregistrez n'importe quelle entrée en fichier texte (.txt) ou document Word (.docx) depuis le menu contextuel.
* **Indicateur de collage** : Les entrées qui ont été collées sont marquées par "Pasted:" dans la liste.
* **Collage combiné** : Lorsque plusieurs entrées sont collées ensemble, le texte combiné est également enregistré comme nouvelle entrée.
* **Historique persistant** : L'historique est sauvegardé entre les sessions NVDA (configurable).
* **Groupes personnalisés** : Créez et gérez des groupes personnalisés pour organiser les entrées.
* **Configurable** : Panneau de paramètres dans les Préférences NVDA pour le nombre maximum d'entrées, la persistance et les annonces.

## Raccourcis clavier globaux

| Raccourci | Action |
|---|---|
| NVDA+A | Ouvrir la boîte de dialogue de l'historique |
| NVDA+C | Annoncer le contenu actuel du presse-papiers |
| NVDA+Shift+A | Ajouter le texte sélectionné à la dernière entrée |
| NVDA+Alt+Flèche haut | Naviguer vers l'entrée précédente |
| NVDA+Alt+Flèche bas | Naviguer vers l'entrée suivante |
| NVDA+Alt+V | Coller l'entrée actuellement sélectionnée |
| NVDA+Alt+Entrée | Copier l'entrée dans le presse-papiers |
| NVDA+Alt+Suppr | Supprimer l'entrée actuellement sélectionnée |
| NVDA+Alt+P | Épingler/désépingler l'entrée |
| NVDA+Alt+X | Effacer tout l'historique |
| NVDA+Alt+G | Définir le groupe de l'entrée |

## Raccourcis clavier dans la boîte de dialogue

Lorsque la boîte de dialogue est ouverte :

| Raccourci | Action |
|---|---|
| Entrée | Coller l'entrée/les entrées sélectionnées |
| Ctrl+Espace | Basculer la sélection multiple (respecte l'ordre) |
| Suppr | Supprimer l'entrée/les entrées sélectionnées |
| Ctrl+P | Épingler/désépingler |
| Ctrl+G | Définir le groupe |
| Shift+Flèche haut | Déplacer l'entrée vers le haut |
| Shift+Flèche bas | Déplacer l'entrée vers le bas |
| Touche Applications | Ouvrir le menu contextuel |
| Alt+S | Focus sur le champ de recherche |
| Alt+U | Focus sur le filtre de groupe |
| Alt+G | Bouton définir le groupe |
| Échap | Fermer la boîte de dialogue |

## Options du menu contextuel

Clic droit ou touche Applications sur n'importe quelle entrée :

* Coller
* Copier dans le presse-papiers
* **Enregistrer sous** sous-menu : Fichier texte (.txt), Document Word (.docx)
* **Déplacer vers** sous-menu : Haut, Bas
* Épingler / Désépingler
* Définir le groupe
* Supprimer

## Paramètres

Disponibles dans menu NVDA > Préférences > Paramètres > Historique du presse-papiers :

* **Nombre maximum d'entrées** : Définir la limite (10–10 000, par défaut 500). Au-delà, l'entrée non épinglée la plus ancienne est supprimée.
* **Sauvegarder l'historique entre les sessions** : Conserver l'historique au redémarrage (par défaut : activé).
* **Annoncer quand un nouveau texte est copié** : Énoncer un aperçu lorsqu'un nouveau contenu est détecté (par défaut : désactivé).

## Compatibilité

* Version minimum de NVDA : 2024.1
* Dernière version testée : NVDA 2025.3

## Licence

Licence publique générale GNU, version 2.
