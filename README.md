# TEI NLP Converter - Proxmox Container Deployment Guide

## Overview

The TEI NLP Converter is a production-ready application that processes natural language text and converts it to TEI XML format with domain-specific schemas. The application features a **multi-provider NLP architecture** with intelligent fallback and provider-specific optimizations.

### Key Features

- **Multi-Provider NLP Architecture**
  - **Google Cloud NLP**: Advanced entity analysis with salience, sentiment, and Knowledge Graph integration
  - **SpaCy (Local)**: Fast, privacy-focused processing with rich morphological features
  - **Remote NLP Server**: Extensible support for custom NLP services
  - **Intelligent Fallback**: Automatic failover between providers

- **Provider-Specific Optimizations**
  - Dynamic entity mapping based on provider capabilities
  - Granularity-aware processing options
  - Google-specific features: entity salience, sentiment, Knowledge Graph MIDs
  - SpaCy-specific features: detailed morphology, dependency parsing

- **Domain-Specific TEI Schemas**
  - Pre-configured schemas for 10+ domains (legal, scientific, literary, etc.)
  - Provider-aware entity-to-TEI mappings
  - Customizable annotation strategies (inline, standoff, mixed)

- **Production-Ready Infrastructure**
  - Comprehensive caching with Redis
  - Database persistence with SQLAlchemy
  - Rate limiting and security features
  - Prometheus metrics and health monitoring
  - Background task processing

### NLP Provider Setup

For **Google Cloud NLP** integration with advanced features:
- See [Google Cloud Setup Guide](GOOGLE_CLOUD_SETUP.md) for detailed instructions
- Includes entity salience, sentiment analysis, and Knowledge Graph integration

For **SpaCy** (default, no setup required):
- Works out of the box with included models
- Ideal for privacy-sensitive deployments

## System Requirements & Architecture Overview

**Application Stack:**
- Python 3.11 FastAPI application
- PostgreSQL 14 (production database)
- Redis 7 (caching layer)
- Nginx (reverse proxy)
- SSL/TLS via Let's Encrypt

---

## 1. Container Creation in Proxmox

### 1.1 Create New Container

```bash
# In Proxmox Web UI or via CLI
pct create 110 local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst \
  --hostname tei-nlp \
  --memory 4096 \
  --cores 2 \
  --rootfs local-lvm:16 \
  --net0 name=eth0,bridge=vmbr0,firewall=1,ip=dhcp,type=veth \
  --onboot 1 \
  --start 1
```

**Recommended Specifications:**
- **OS Template**: Ubuntu 22.04 LTS
- **RAM**: 4GB minimum (8GB recommended for production)
- **CPU Cores**: 2 minimum (4 recommended)
- **Disk**: 16GB minimum (32GB recommended)
- **Network**: Bridged mode with DHCP or static IP
- **Hostname**: tei-nlp

### 1.2 Initial Container Access

```bash
# From Proxmox host
pct enter 110

# Or SSH if configured
ssh root@<container-ip>
```

---

## 2. System Preparation

### 2.1 Update System

```bash
apt update && apt upgrade -y
apt install -y software-properties-common curl wget git vim
```

### 2.2 Install Python 3.11

```bash
# Add deadsnakes PPA for Python 3.11
add-apt-repository ppa:deadsnakes/ppa -y
apt update

# Install Python 3.11 and dependencies
apt install -y python3.11 python3.11-venv python3.11-dev python3-pip
apt install -y build-essential libssl-dev libffi-dev
```

### 2.3 Install System Dependencies

```bash
# PostgreSQL 14
sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
apt update
apt install -y postgresql-14 postgresql-client-14

# Redis
apt install -y redis-server

# Nginx
apt install -y nginx certbot python3-certbot-nginx

# Additional tools
apt install -y supervisor htop ncdu
```

---

## 3. Application Setup

### 3.1 Create Application User

```bash
# Create dedicated user for security
useradd -m -s /bin/bash teiapp
usermod -aG sudo teiapp

# Set password
passwd teiapp
```

### 3.2 Setup Directory Structure

```bash
# Switch to app user
su - teiapp

# Create application directory
sudo mkdir -p /opt/tei-nlp-converter
sudo chown -R teiapp:teiapp /opt/tei-nlp-converter
cd /opt/tei-nlp-converter

# Create required directories
sudo mkdir -p nlp_providers migrations/versions schemas templates static tests kubernetes logs data ssl
```

### 3.3 Copy Application Code

```bash
# Option A: Clone from git (if hosted)
git clone https://your-repo/tei-nlp-converter.git .

# Option B: Copy files via SCP
# From your local machine:
scp -r /path/to/tei-nlp-converter/* teiapp@<container-ip>:/opt/tei-nlp-converter/
```

### 3.4 Create Python Virtual Environment

```bash
cd /opt/tei-nlp-converter
python3.11 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip setuptools wheel
```

### 3.5 Install Python Dependencies

```bash
# Install requirements
pip install -r requirements.txt

# Download SpaCy model
python -m spacy download en_core_web_sm
```

### 3.6 Configure PostgreSQL

```bash
# Switch to postgres user
sudo -u postgres psql

-- Create database and user
CREATE USER tei_user WITH PASSWORD 'CHANGE_THIS_STRONG_PASSWORD';
CREATE DATABASE tei_nlp OWNER tei_user;
GRANT ALL PRIVILEGES ON DATABASE tei_nlp TO tei_user;
\q
```

### 3.7 Configure Redis

```bash
# Edit Redis configuration
sudo vim /etc/redis/redis.conf

# Set these values:
bind 127.0.0.1
protected-mode yes
maxmemory 512mb
maxmemory-policy allkeys-lru

# Restart Redis
sudo systemctl restart redis-server
sudo systemctl enable redis-server
```

### 3.8 Setup Environment Variables

```bash
cd /opt/tei-nlp-converter

# Copy environment template
cp .env.example .env

# Generate secure keys
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))" >> .env.tmp
python3 -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(32))" >> .env.tmp
python3 -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())" >> .env.tmp

# Edit .env file
vim .env
```

**Key configurations in .env:**
```bash
APP_NAME="TEI NLP Converter"
ENVIRONMENT=production
DEBUG=false
HOST=0.0.0.0
PORT=8080

DATABASE_URL=postgresql://tei_user:CHANGE_THIS_STRONG_PASSWORD@localhost:5432/tei_nlp
REDIS_URL=redis://localhost:6379/0

# Copy the generated keys from .env.tmp
SECRET_KEY=<generated-key>
SESSION_SECRET=<generated-key>
ENCRYPTION_KEY=<generated-key>
```

### 3.9 Initialize Database

```bash
source venv/bin/activate
cd /opt/tei-nlp-converter

# Run migrations
alembic upgrade head

# Or if alembic.ini doesn't exist, initialize database directly
python -c "from storage import Storage; s = Storage(); s.init_db()"
```

---

## 4. Service Management

### 4.1 Create Systemd Service

```bash
sudo vim /etc/systemd/system/tei-nlp.service
```

```ini
[Unit]
Description=TEI NLP Converter
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
Type=forking
User=teiapp
Group=teiapp
WorkingDirectory=/opt/tei-nlp-converter
Environment="PATH=/opt/tei-nlp-converter/venv/bin"
ExecStart=/opt/tei-nlp-converter/venv/bin/gunicorn \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 127.0.0.1:8080 \
    --daemon \
    --pid /opt/tei-nlp-converter/gunicorn.pid \
    --access-logfile /opt/tei-nlp-converter/logs/access.log \
    --error-logfile /opt/tei-nlp-converter/logs/error.log \
    app:app

ExecReload=/bin/kill -s HUP $MAINPID
ExecStop=/bin/kill -s TERM $MAINPID
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 4.2 Install and Configure Gunicorn

```bash
source /opt/tei-nlp-converter/venv/bin/activate
pip install gunicorn
```

### 4.3 Configure Nginx Reverse Proxy

```bash
sudo vim /etc/nginx/sites-available/tei-nlp
```

```nginx
upstream tei_backend {
    server 127.0.0.1:8080;
}

server {
    listen 80;
    server_name your-domain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL configuration (will be managed by Certbot)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Increase upload size for text processing
    client_max_body_size 10M;
    
    # Static files
    location /static {
        alias /opt/tei-nlp-converter/static;
        expires 1d;
    }
    
    # Application
    location / {
        proxy_pass http://tei_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### 4.4 Enable Services

```bash
# Enable Nginx site
sudo ln -s /etc/nginx/sites-available/tei-nlp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Start and enable application service
sudo systemctl daemon-reload
sudo systemctl enable tei-nlp
sudo systemctl start tei-nlp

# Check status
sudo systemctl status tei-nlp
```

### 4.5 Setup SSL with Let's Encrypt

```bash
# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com

# Test renewal
sudo certbot renew --dry-run
```

---

## 5. Security Hardening

### 5.1 Configure Firewall

```bash
# Install and configure UFW
sudo apt install -y ufw

# Allow necessary ports
sudo ufw allow 22/tcp     # SSH
sudo ufw allow 80/tcp     # HTTP
sudo ufw allow 443/tcp    # HTTPS

# Enable firewall
sudo ufw --force enable
sudo ufw status
```

### 5.2 Secure SSH Access

```bash
# Edit SSH configuration
sudo vim /etc/ssh/sshd_config

# Set these values:
PermitRootLogin no
PasswordAuthentication no  # After setting up SSH keys
PubkeyAuthentication yes
MaxAuthTries 3

# Restart SSH
sudo systemctl restart sshd
```

### 5.3 Setup SSH Keys

```bash
# On your local machine
ssh-copy-id teiapp@<container-ip>

# Test SSH key login
ssh teiapp@<container-ip>
```

### 5.4 Application Security

```bash
# Set secure permissions
chmod 600 /opt/tei-nlp-converter/.env
chmod 700 /opt/tei-nlp-converter/logs
chmod 700 /opt/tei-nlp-converter/data
```

### 5.5 Setup Log Rotation

```bash
sudo vim /etc/logrotate.d/tei-nlp
```

```
/opt/tei-nlp-converter/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 640 teiapp teiapp
    sharedscripts
    postrotate
        systemctl reload tei-nlp > /dev/null 2>&1 || true
    endscript
}
```

---

## 6. Validation & Monitoring

### 6.1 Test Application

```bash
# Check service status
sudo systemctl status tei-nlp

# Test local access
curl -I http://localhost:8080/health

# Check logs
tail -f /opt/tei-nlp-converter/logs/tei_nlp.log
tail -f /var/log/nginx/access.log
```

### 6.2 Test Internet Access

```bash
# From external machine
curl https://your-domain.com/health

# Expected response:
{
  "status": "healthy",
  "version": "2.1.0",
  "services": {...}
}
```

### 6.3 Monitor Resources

```bash
# Check resource usage
htop

# Check disk usage
df -h
ncdu /opt/tei-nlp-converter

# Monitor logs
journalctl -u tei-nlp -f
```

### 6.4 Setup Health Check Script

```bash
vim /opt/tei-nlp-converter/healthcheck.sh
```

```bash
#!/bin/bash
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health)
if [ $response != "200" ]; then
    echo "Health check failed with status $response"
    systemctl restart tei-nlp
fi
```

```bash
chmod +x /opt/tei-nlp-converter/healthcheck.sh

# Add to crontab
crontab -e
*/5 * * * * /opt/tei-nlp-converter/healthcheck.sh
```

---

## 7. Maintenance Commands

### Service Management
```bash
# Start/Stop/Restart
sudo systemctl start tei-nlp
sudo systemctl stop tei-nlp
sudo systemctl restart tei-nlp

# View logs
sudo journalctl -u tei-nlp -n 100
```

### Database Backup
```bash
# Backup database
pg_dump -U tei_user tei_nlp > backup_$(date +%Y%m%d).sql

# Restore database
psql -U tei_user tei_nlp < backup.sql
```

### Application Updates
```bash
cd /opt/tei-nlp-converter
source venv/bin/activate

# Update code
git pull  # or copy new files

# Update dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Restart service
sudo systemctl restart tei-nlp
```

---

## Troubleshooting

**Service won't start:**
```bash
sudo journalctl -u tei-nlp -n 50
cat /opt/tei-nlp-converter/logs/error.log
```

**Database connection issues:**
```bash
sudo -u postgres psql -c "\l"  # List databases
sudo -u postgres psql -c "\du"  # List users
```

**Port already in use:**
```bash
sudo lsof -i :8080
sudo kill -9 <PID>
```

The application should now be running and accessible from the Internet at `https://your-domain.com`.
