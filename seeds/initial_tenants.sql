CREATE TABLE IF NOT EXISTS public.tenants (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(100) UNIQUE NOT NULL,
    db_schema VARCHAR(100) UNIQUE NOT NULL
);

INSERT INTO public.tenants (name, tenant_id, db_schema) VALUES
('Tenant A', 'tenant_a', 'schema_tenant_a'),
('Tenant B', 'tenant_b', 'schema_tenant_b')
ON CONFLICT (tenant_id) DO NOTHING;
