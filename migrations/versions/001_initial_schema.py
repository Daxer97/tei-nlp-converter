"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create initial database schema with all tables and indexes"""
    
    # Create ENUM type for task status
    task_status_enum = postgresql.ENUM(
        'pending', 'processing', 'completed', 'failed', 'cancelled',
        name='taskstatus',
        create_type=True
    )
    
    # Create processed_texts table
    op.create_table(
        'processed_texts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('domain', sa.String(50), nullable=False),
        sa.Column('nlp_results', sa.Text(), nullable=False),
        sa.Column('tei_xml', sa.Text(), nullable=False),
        sa.Column('text_hash', sa.String(64), nullable=True),
        sa.Column('processing_time', sa.Float(), nullable=True),
        sa.Column('request_id', sa.String(36), nullable=True),
        sa.Column('user_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for processed_texts
    op.create_index('idx_processed_texts_id', 'processed_texts', ['id'])
    op.create_index('idx_processed_texts_domain', 'processed_texts', ['domain'])
    op.create_index('idx_processed_texts_text_hash', 'processed_texts', ['text_hash'])
    op.create_index('idx_processed_texts_request_id', 'processed_texts', ['request_id'])
    op.create_index('idx_processed_texts_user_id', 'processed_texts', ['user_id'])
    op.create_index('idx_processed_texts_created_at', 'processed_texts', ['created_at'])
    op.create_index('idx_domain_created', 'processed_texts', ['domain', 'created_at'])
    op.create_index('idx_hash_domain', 'processed_texts', ['text_hash', 'domain'])
    op.create_index('idx_user_created', 'processed_texts', ['user_id', 'created_at'])
    
    # Create background_tasks table
    op.create_table(
        'background_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.String(36), nullable=False, unique=True),
        sa.Column('status', task_status_enum, nullable=False, server_default='pending'),
        sa.Column('input_data', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('request_id', sa.String(36), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id')
    )
    
    # Create indexes for background_tasks
    op.create_index('idx_background_tasks_id', 'background_tasks', ['id'])
    op.create_index('idx_background_tasks_task_id', 'background_tasks', ['task_id'])
    op.create_index('idx_background_tasks_created_at', 'background_tasks', ['created_at'])
    op.create_index('idx_task_status_created', 'background_tasks', ['status', 'created_at'])
    op.create_index('idx_request_id', 'background_tasks', ['request_id'])
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column('request_id', sa.String(36), nullable=True),
        sa.Column('user_id', sa.String(255), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=True),
        sa.Column('resource_id', sa.String(100), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for audit_logs
    op.create_index('idx_audit_logs_id', 'audit_logs', ['id'])
    op.create_index('idx_audit_logs_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('idx_audit_logs_request_id', 'audit_logs', ['request_id'])
    op.create_index('idx_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_user_timestamp', 'audit_logs', ['user_id', 'timestamp'])
    op.create_index('idx_audit_action_timestamp', 'audit_logs', ['action', 'timestamp'])
    
    # Create performance monitoring table (optional)
    op.create_table(
        'performance_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('endpoint', sa.String(100), nullable=False),
        sa.Column('method', sa.String(10), nullable=False),
        sa.Column('response_time_ms', sa.Float(), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(36), nullable=True),
        sa.Column('user_id', sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('idx_perf_timestamp', 'performance_metrics', ['timestamp'])
    op.create_index('idx_perf_endpoint', 'performance_metrics', ['endpoint'])
    
    # Create triggers for updated_at columns (PostgreSQL specific)
    if op.get_context().dialect.name == 'postgresql':
        op.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)
        
        op.execute("""
            CREATE TRIGGER update_processed_texts_updated_at 
            BEFORE UPDATE ON processed_texts 
            FOR EACH ROW 
            EXECUTE FUNCTION update_updated_at_column();
        """)
    
    # Create partitioning for audit_logs by month (PostgreSQL 12+)
    if op.get_context().dialect.name == 'postgresql':
        try:
            op.execute("""
                -- Convert audit_logs to partitioned table
                ALTER TABLE audit_logs 
                RENAME TO audit_logs_old;
                
                CREATE TABLE audit_logs (
                    id SERIAL,
                    timestamp TIMESTAMP DEFAULT NOW(),
                    request_id VARCHAR(36),
                    user_id VARCHAR(255),
                    action VARCHAR(100) NOT NULL,
                    resource_type VARCHAR(50),
                    resource_id VARCHAR(100),
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    status_code INTEGER,
                    error_message TEXT,
                    metadata JSON,
                    PRIMARY KEY (id, timestamp)
                ) PARTITION BY RANGE (timestamp);
                
                -- Create initial partitions
                CREATE TABLE audit_logs_2024_01 PARTITION OF audit_logs
                    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
                CREATE TABLE audit_logs_2024_02 PARTITION OF audit_logs
                    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
                CREATE TABLE audit_logs_2024_03 PARTITION OF audit_logs
                    FOR VALUES FROM ('2024-03-01') TO ('2024-04-01');
                
                -- Copy data from old table
                INSERT INTO audit_logs SELECT * FROM audit_logs_old;
                
                -- Drop old table
                DROP TABLE audit_logs_old;
                
                -- Recreate indexes on partitioned table
                CREATE INDEX idx_audit_timestamp_part ON audit_logs (timestamp);
                CREATE INDEX idx_audit_user_part ON audit_logs (user_id, timestamp);
            """)
        except:
            # If partitioning fails, keep regular table
            pass


def downgrade():
    """Drop all tables and types"""
    
    # Drop tables
    op.drop_table('performance_metrics')
    op.drop_table('audit_logs')
    op.drop_table('background_tasks')
    op.drop_table('processed_texts')
    
    # Drop enum type
    if op.get_context().dialect.name == 'postgresql':
        op.execute("DROP TYPE IF EXISTS taskstatus")
        
        # Drop trigger function
        op.execute("DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE")
