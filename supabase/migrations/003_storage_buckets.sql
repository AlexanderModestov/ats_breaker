-- Storage buckets for HR-Breaker
-- Creates buckets for CVs and results with appropriate policies

-- Note: Storage bucket creation is typically done via Supabase Dashboard or CLI
-- This file documents the required configuration

-- Create CVs bucket (private - user files)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'cvs',
    'cvs',
    false,
    10485760, -- 10MB limit
    ARRAY['application/pdf', 'text/plain', 'text/x-tex', 'text/markdown', 'text/html']
)
ON CONFLICT (id) DO NOTHING;

-- Create results bucket (private - generated PDFs)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'results',
    'results',
    false,
    10485760, -- 10MB limit
    ARRAY['application/pdf']
)
ON CONFLICT (id) DO NOTHING;

-- Storage policies for CVs bucket
-- Users can upload to their own folder
CREATE POLICY "Users can upload CVs to own folder"
    ON storage.objects FOR INSERT
    WITH CHECK (
        bucket_id = 'cvs'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

-- Users can view their own CVs
CREATE POLICY "Users can view own CVs"
    ON storage.objects FOR SELECT
    USING (
        bucket_id = 'cvs'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

-- Users can delete their own CVs
CREATE POLICY "Users can delete own CVs"
    ON storage.objects FOR DELETE
    USING (
        bucket_id = 'cvs'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

-- Storage policies for results bucket
-- Users can view their own results
CREATE POLICY "Users can view own results"
    ON storage.objects FOR SELECT
    USING (
        bucket_id = 'results'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

-- Service role can upload results (backend creates these)
-- Note: Service role bypasses RLS, so no explicit policy needed for uploads
