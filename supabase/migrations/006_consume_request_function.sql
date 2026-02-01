-- Atomic function to consume a request from user's quota
-- Prevents race conditions with concurrent requests

CREATE OR REPLACE FUNCTION consume_request(
    p_user_id UUID,
    p_is_subscriber BOOLEAN,
    p_subscription_limit INTEGER DEFAULT 50
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    rows_affected INTEGER;
BEGIN
    IF p_is_subscriber THEN
        -- Try to increment period_request_count if under limit
        UPDATE profiles
        SET period_request_count = period_request_count + 1
        WHERE id = p_user_id
          AND period_request_count < p_subscription_limit;

        GET DIAGNOSTICS rows_affected = ROW_COUNT;

        IF rows_affected > 0 THEN
            RETURN TRUE;
        END IF;

        -- Period quota exhausted, try addon credits
        UPDATE profiles
        SET addon_credits = addon_credits - 1
        WHERE id = p_user_id
          AND addon_credits > 0;

        GET DIAGNOSTICS rows_affected = ROW_COUNT;
        RETURN rows_affected > 0;
    ELSE
        -- Trial user: increment request_count (no limit check here, done in app)
        UPDATE profiles
        SET request_count = request_count + 1
        WHERE id = p_user_id;

        GET DIAGNOSTICS rows_affected = ROW_COUNT;
        RETURN rows_affected > 0;
    END IF;
END;
$$;

-- Function to atomically add addon credits
CREATE OR REPLACE FUNCTION add_addon_credits(
    p_user_id UUID,
    p_credits INTEGER
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    rows_affected INTEGER;
BEGIN
    UPDATE profiles
    SET addon_credits = addon_credits + p_credits
    WHERE id = p_user_id;

    GET DIAGNOSTICS rows_affected = ROW_COUNT;
    RETURN rows_affected > 0;
END;
$$;
