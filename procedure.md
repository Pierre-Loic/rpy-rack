# Etapes de paramètrage des Raspberry Pi

## 1. Préparation de la carte micro-SD

Au moins 16 ou 32 Go pour mettre le système d'exploitation, les modèles Ollama, le code de l'API, les conteneurs Docker

- Formatage de carte micro-SD en FAT32

- Utilisation du logiciel Raspberry Pi Imager pour installer le système d'exploitation sur la carte micro-SD avec les réglages suivants :

    - Rpi 5
    - Ubuntu server 25.10 (64 bits) version 2025-10-09
    - Hostname : fonction du Raspberry Pi, exemple : refroidissement_passif_air
    - User : miai
    - Pwd : ****
    - Wifi + SSH avec user et pwd

## 2. Réglage de l'adresse IP fixe pour connexion filaire


- Se connecter en SSH avec la connexion Wifi (routeur Wifi téléphone) : récupérer l'adresse IP locale du Raspberry Pi et se connecter en SSH avec les réglages définis à la création de la carte micro-SD

- Changer l'adresse IP en adresse IP fixe (192.168.137.10 pour le refroidissement passif à l'air, 192.168.137.11 pour le refroidissement actif à l'air et 192.168.137.12 pour le refroidissement actif à l'eau)

Modifier ce fichier :

```
sudo nano /etc/netplan/50-cloud-init.yaml
```

Avec ce contenu (conserver les réglages Wifi):

```bash
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: no
      addresses:
        - 192.168.137.10/24
      gateway4: 192.168.137.1
      nameservers:
        addresses:
          - 1.1.1.1
          - 8.8.8.8
```

Appliquer la configuration :

```bash
sudo netplan try
```

## 3. Connexion SSH en filaire RJ45

- Connexion en SSH en filaire sur l'adresse 192.168.137.10 (peut nécessiter une mise à jour des known hosts)

- Effectuer les mises à jour des logiciels :

Mettre à jour la liste des paquets

```bash
sudo apt update
```

Mettre à jour les paquets installés

```bash
sudo apt upgrade
```

## 4. Installation de Docker et Docker Compose

- Installer les dépendances nécessaires :

```bash
sudo apt install -y \
  ca-certificates \
  curl \
  gnupg \
  lsb-release
```

- Ajouter la clé GPG officielle Docker

```bash
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
```

```bash
sudo chmod a+r /etc/apt/keyrings/docker.gpg
```

- Ajouter le dépôt Docker (ARM64 compatible)

```bash
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

```bash
sudo apt update
```

- Installer Docker Engine + Docker Compose

```bash
sudo apt install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin
```

- Vérifier l’installation

```bash
docker --version
```

```bash
docker compose version
```

- Utiliser Docker sans sudo

```bash
sudo usermod -aG docker $USER
```

```bash
newgrp docker
```

```bash
docker run hello-world
```

- Activer Docker au démarrage

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

## 5. Récupération du dépôt Git avec le code Docker-compose avec les conteneur Fast-API et Ollama

Le dépôt à récupérer est le dépôt Github privé : https://github.com/Pierre-Loic/rpy-rack

- Générer une clé SSH sur le Raspberry Pi




## 6. Installation des modèles Ollama utiles pour la maquette

