"""
secrets_manager.py - Secure secrets management with enhanced security
"""
import os
import json
import base64
import platform
from typing import Any, Optional, Dict
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
import hvac
import boto3
from botocore.exceptions import ClientError
from logger import get_logger
import stat

logger = get_logger(__name__)

class SecretsBackend:
    """Base class for secrets backends"""
    
    def get(self, key: str) -> Optional[str]:
        raise NotImplementedError
    
    def set(self, key: str, value: str) -> bool:
        raise NotImplementedError
    
    def delete(self, key: str) -> bool:
        raise NotImplementedError
    
    def list_keys(self) -> list:
        raise NotImplementedError

class EnvironmentBackend(SecretsBackend):
    """Environment variables backend (for development)"""
    
    def get(self, key: str) -> Optional[str]:
        return os.environ.get(key)
    
    def set(self, key: str, value: str) -> bool:
        os.environ[key] = value
        return True
    
    def delete(self, key: str) -> bool:
        if key in os.environ:
            del os.environ[key]
            return True
        return False
    
    def list_keys(self) -> list:
        return list(os.environ.keys())

class FileBackend(SecretsBackend):
    """Encrypted file-based backend with enhanced security"""
    
    def __init__(self, file_path: str = ".secrets.enc", master_key: Optional[str] = None):
        self.file_path = Path(file_path)
        
        # Generate or load encryption key
        if master_key:
            self.cipher = Fernet(master_key.encode() if isinstance(master_key, str) else master_key)
        else:
            key_file = Path(".secrets.key")
            if key_file.exists():
                # Verify key file permissions
                self._verify_file_permissions(key_file)
                with open(key_file, 'rb') as f:
                    self.cipher = Fernet(f.read())
            else:
                key = Fernet.generate_key()
                with open(key_file, 'wb') as f:
                    f.write(key)
                self._secure_file_permissions(key_file)
                self.cipher = Fernet(key)
                logger.warning(f"Generated new master key at {key_file}. Keep this secure!")
        
        self._load_secrets()

    def _load_secrets(self):
    """Load secrets from encrypted file"""
        self.secrets = {}
        if self.file_path.exists():
            try:
                self._verify_file_permissions(self.file_path)
                with open(self.file_path, 'rb') as f:
                    encrypted_data = f.read()
                if encrypted_data:
                    decrypted_data = self.cipher.decrypt(encrypted_data)
                    self.secrets = json.loads(decrypted_data)
            except Exception as e:
                logger.error(f"Failed to load secrets: {e}")
                self.secrets = {}
    
    def _secure_file_permissions(self, file_path: Path):
        """Set secure file permissions (platform-aware)"""
        if platform.system() != 'Windows':
            try:
                # Set read/write for owner only
                os.chmod(file_path, stat.S_IRUSR | stat.S_IWUSR)
                
                # Verify permissions were set correctly
                actual_mode = file_path.stat().st_mode
                if actual_mode & 0o077:
                    logger.error(f"Failed to set secure permissions on {file_path}")
                    raise PermissionError(f"Could not secure {file_path}")
            except Exception as e:
                logger.error(f"Failed to set file permissions: {e}")
                raise
        else:
            # Windows: Use different approach
            try:
                import win32security
                import ntsecuritycon as con
                
                # Get current user SID
                username = os.environ.get('USERNAME')
                domain = os.environ.get('USERDOMAIN', '')
                
                # Set ACL to current user only
                sd = win32security.GetFileSecurity(str(file_path), win32security.DACL_SECURITY_INFORMATION)
                dacl = win32security.ACL()
                
                # Add permission for current user
                user_sid = win32security.LookupAccountName(domain, username)[0]
                dacl.AddAccessAllowedAce(
                    win32security.ACL_REVISION,
                    con.FILE_GENERIC_READ | con.FILE_GENERIC_WRITE,
                    user_sid
                )
                
                sd.SetSecurityDescriptorDacl(1, dacl, 0)
                win32security.SetFileSecurity(str(file_path), win32security.DACL_SECURITY_INFORMATION, sd)
            except ImportError:
                logger.warning("pywin32 not installed, cannot set Windows file permissions")
            except Exception as e:
                logger.warning(f"Could not set Windows file permissions: {e}")
    
    def _verify_file_permissions(self, file_path: Path):
        """Verify file has secure permissions"""
        if platform.system() != 'Windows':
            mode = file_path.stat().st_mode
            if mode & 0o077:
                logger.warning(
                    f"File {file_path} has insecure permissions: {oct(mode)}. "
                    f"Consider running: chmod 600 {file_path}"
                )
    
    def _save_secrets(self):
        """Encrypt and save secrets to file with secure permissions"""
        try:
            data = json.dumps(self.secrets).encode()
            encrypted_data = self.cipher.encrypt(data)
            
            # Write atomically using temp file
            temp_file = self.file_path.with_suffix('.tmp')
            with open(temp_file, 'wb') as f:
                f.write(encrypted_data)
            
            # Set secure permissions before rename
            self._secure_file_permissions(temp_file)
            
            # Atomic rename
            temp_file.replace(self.file_path)
            
            return True
        except Exception as e:
            logger.error(f"Failed to save secrets: {e}")
            # Clean up temp file if it exists
            temp_file = self.file_path.with_suffix('.tmp')
            if temp_file.exists():
                temp_file.unlink()
            return False



class HashiCorpVaultBackend(SecretsBackend):
    """HashiCorp Vault backend for production"""
    
    def __init__(self, vault_url: str, vault_token: str, mount_point: str = "secret"):
        self.client = hvac.Client(url=vault_url, token=vault_token)
        self.mount_point = mount_point
        
        if not self.client.is_authenticated():
            raise ValueError("Failed to authenticate with Vault")
        
        logger.info(f"Connected to Vault at {vault_url}")
    
    def get(self, key: str) -> Optional[str]:
        try:
            response = self.client.secrets.kv.v2.read_secret_version(
                path=key,
                mount_point=self.mount_point
            )
            return response['data']['data'].get('value')
        except Exception as e:
            logger.debug(f"Secret not found: {key}")
            return None
    
    def set(self, key: str, value: str) -> bool:
        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=key,
                secret={'value': value},
                mount_point=self.mount_point
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set secret {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        try:
            self.client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=key,
                mount_point=self.mount_point
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete secret {key}: {e}")
            return False
    
    def list_keys(self) -> list:
        try:
            response = self.client.secrets.kv.v2.list_secrets(
                path='',
                mount_point=self.mount_point
            )
            return response.get('data', {}).get('keys', [])
        except Exception:
            return []

class AWSSecretsManagerBackend(SecretsBackend):
    """AWS Secrets Manager backend"""
    
    def __init__(self, region_name: str = 'us-east-1', prefix: str = 'tei-nlp/'):
        self.client = boto3.client('secretsmanager', region_name=region_name)
        self.prefix = prefix
    
    def _get_secret_name(self, key: str) -> str:
        """Get full secret name with prefix"""
        return f"{self.prefix}{key}"
    
    def get(self, key: str) -> Optional[str]:
        try:
            secret_name = self._get_secret_name(key)
            response = self.client.get_secret_value(SecretId=secret_name)
            
            if 'SecretString' in response:
                secret = json.loads(response['SecretString'])
                return secret.get('value')
            else:
                # Binary secret
                return base64.b64decode(response['SecretBinary']).decode()
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.debug(f"Secret not found: {key}")
            else:
                logger.error(f"AWS Secrets Manager error: {e}")
            return None
    
    def set(self, key: str, value: str) -> bool:
        try:
            secret_name = self._get_secret_name(key)
            secret_data = json.dumps({'value': value})
            
            # Try to update existing secret
            try:
                self.client.update_secret(
                    SecretId=secret_name,
                    SecretString=secret_data
                )
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    # Create new secret
                    self.client.create_secret(
                        Name=secret_name,
                        SecretString=secret_data
                    )
                else:
                    raise
            
            return True
        except Exception as e:
            logger.error(f"Failed to set secret {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        try:
            secret_name = self._get_secret_name(key)
            self.client.delete_secret(
                SecretId=secret_name,
                ForceDeleteWithoutRecovery=True
            )
            return True
        except ClientError as e:
            logger.error(f"Failed to delete secret {key}: {e}")
            return False
    
    def list_keys(self) -> list:
        try:
            paginator = self.client.get_paginator('list_secrets')
            secrets = []
            
            for page in paginator.paginate():
                for secret in page['SecretList']:
                    name = secret['Name']
                    if name.startswith(self.prefix):
                        key = name[len(self.prefix):]
                        secrets.append(key)
            
            return secrets
        except Exception as e:
            logger.error(f"Failed to list secrets: {e}")
            return []

class SecretsManager:
    """
    Main secrets manager that provides a unified interface
    """
    
    def __init__(self, backend: Optional[str] = None):
        self.backend = self._initialize_backend(backend)
        self._cache = {}  # In-memory cache for frequently accessed secrets
    
    def _initialize_backend(self, backend_type: Optional[str]) -> SecretsBackend:
        """Initialize the appropriate backend based on configuration"""
        backend_type = backend_type or os.environ.get('SECRETS_BACKEND', 'env')
        
        if backend_type == 'env':
            logger.info("Using environment variables for secrets")
            return EnvironmentBackend()
        
        elif backend_type == 'file':
            logger.info("Using encrypted file backend for secrets")
            return FileBackend()
        
        elif backend_type == 'vault':
            vault_url = os.environ.get('VAULT_URL')
            vault_token = os.environ.get('VAULT_TOKEN')
            
            if not vault_url or not vault_token:
                logger.warning("Vault configuration missing, falling back to file backend")
                return FileBackend()
            
            try:
                return HashiCorpVaultBackend(vault_url, vault_token)
            except Exception as e:
                logger.error(f"Failed to initialize Vault: {e}, falling back to file backend")
                return FileBackend()
        
        elif backend_type == 'aws':
            try:
                return AWSSecretsManagerBackend()
            except Exception as e:
                logger.error(f"Failed to initialize AWS Secrets Manager: {e}, falling back to file backend")
                return FileBackend()
        
        else:
            logger.warning(f"Unknown backend type: {backend_type}, using environment")
            return EnvironmentBackend()
    
    def get(self, key: str, default: Optional[str] = None, use_cache: bool = True) -> Optional[str]:
        """Get a secret value"""
        # Check cache first
        if use_cache and key in self._cache:
            return self._cache[key]
        
        value = self.backend.get(key)
        
        if value is None:
            value = default
        
        # Cache the value
        if use_cache and value is not None:
            self._cache[key] = value
        
        return value
    
    def set(self, key: str, value: str) -> bool:
        """Set a secret value"""
        success = self.backend.set(key, value)
        
        if success:
            # Update cache
            self._cache[key] = value
        
        return success
    
    def delete(self, key: str) -> bool:
        """Delete a secret"""
        success = self.backend.delete(key)
        
        if success and key in self._cache:
            del self._cache[key]
        
        return success
    
    def get_many(self, keys: list, defaults: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
        """Get multiple secrets at once"""
        defaults = defaults or {}
        result = {}
        
        for key in keys:
            result[key] = self.get(key, defaults.get(key))
        
        return result
    
    def set_many(self, secrets: Dict[str, str]) -> Dict[str, bool]:
        """Set multiple secrets at once"""
        result = {}
        
        for key, value in secrets.items():
            result[key] = self.set(key, value)
        
        return result
    
    def rotate_secret(self, key: str, new_value: str, keep_old: bool = True) -> bool:
        """Rotate a secret, optionally keeping the old value"""
        if keep_old:
            old_value = self.get(key)
            if old_value:
                self.set(f"{key}_previous", old_value)
        
        return self.set(key, new_value)
    
    def clear_cache(self):
        """Clear the in-memory cache"""
        self._cache.clear()
    
    def list_keys(self) -> list:
        """List all available secret keys"""
        return self.backend.list_keys()
    
    def validate_required_secrets(self, required_keys: list) -> Dict[str, bool]:
        """Validate that required secrets are present"""
        result = {}
        
        for key in required_keys:
            value = self.get(key)
            result[key] = value is not None
        
        missing = [k for k, v in result.items() if not v]
        if missing:
            logger.warning(f"Missing required secrets: {', '.join(missing)}")
        
        return result

# Global instance
_secrets_manager = None

def get_secrets_manager() -> SecretsManager:
    """Get the global secrets manager instance"""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager

def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Convenience function to get a secret"""
    return get_secrets_manager().get(key, default)

def set_secret(key: str, value: str) -> bool:
    """Convenience function to set a secret"""
    return get_secrets_manager().set(key, value)
