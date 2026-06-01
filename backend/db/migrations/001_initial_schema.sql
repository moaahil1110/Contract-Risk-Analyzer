-- Initial Schema for Contract Risk Analyser
-- Week 3: Supabase Integration

-- User profiles table (extends auth.users)
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id),
    email TEXT NOT NULL,
    analyses_used INTEGER DEFAULT 0,
    plan TEXT DEFAULT 'free',  -- 'free' | 'paid'
    created_at TIMESTAMP DEFAULT NOW()
);

-- Contracts table
CREATE TABLE contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id),
    filename TEXT NOT NULL,
    contract_type TEXT,          -- 'nda' | 'employment' | 'vendor' | 'other'
    status TEXT DEFAULT 'processing',  -- 'processing' | 'complete' | 'failed'
    health_score INTEGER,
    health_grade TEXT,
    health_label TEXT,
    total_clauses INTEGER,
    high_risk_count INTEGER DEFAULT 0,
    medium_risk_count INTEGER DEFAULT 0,
    low_risk_count INTEGER DEFAULT 0,
    uploaded_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Individual Clause Analyses table
CREATE TABLE clause_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id UUID REFERENCES contracts(id) ON DELETE CASCADE,
    clause_index INTEGER,         -- Order in document
    clause_title TEXT,
    original_text TEXT NOT NULL,
    risk_level TEXT NOT NULL,     -- 'high' | 'medium' | 'low'
    risk_score INTEGER,
    risk_reason TEXT,
    plain_english TEXT,
    key_concerns JSONB,           -- Array of strings
    suggested_fix TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_contracts_user ON contracts(user_id);
CREATE INDEX idx_clauses_contract ON clause_analyses(contract_id);
CREATE INDEX idx_clauses_risk ON clause_analyses(risk_level);

-- Enable Row Level Security (RLS)
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE clause_analyses ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user_profiles
CREATE POLICY "Users can view own profile" 
    ON user_profiles FOR SELECT 
    USING (auth.uid() = id);

CREATE POLICY "Users can insert own profile" 
    ON user_profiles FOR INSERT 
    WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can update own profile" 
    ON user_profiles FOR UPDATE 
    USING (auth.uid() = id);

-- RLS Policies for contracts
CREATE POLICY "Users can view own contracts" 
    ON contracts FOR SELECT 
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own contracts" 
    ON contracts FOR INSERT 
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own contracts" 
    ON contracts FOR UPDATE 
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own contracts" 
    ON contracts FOR DELETE 
    USING (auth.uid() = user_id);

-- RLS Policies for clause_analyses (via contract ownership)
CREATE POLICY "Users can view clauses of own contracts" 
    ON clause_analyses FOR SELECT 
    USING (EXISTS (
        SELECT 1 FROM contracts 
        WHERE contracts.id = clause_analyses.contract_id 
        AND contracts.user_id = auth.uid()
    ));

CREATE POLICY "Users can insert clauses of own contracts" 
    ON clause_analyses FOR INSERT 
    WITH CHECK (EXISTS (
        SELECT 1 FROM contracts 
        WHERE contracts.id = clause_analyses.contract_id 
        AND contracts.user_id = auth.uid()
    ));

CREATE POLICY "Users can update clauses of own contracts" 
    ON clause_analyses FOR UPDATE 
    USING (EXISTS (
        SELECT 1 FROM contracts 
        WHERE contracts.id = clause_analyses.contract_id 
        AND contracts.user_id = auth.uid()
    ));

CREATE POLICY "Users can delete clauses of own contracts" 
    ON clause_analyses FOR DELETE 
    USING (EXISTS (
        SELECT 1 FROM contracts 
        WHERE contracts.id = clause_analyses.contract_id 
        AND contracts.user_id = auth.uid()
    ));
