-- Application Tracker Database Schema
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    apply_url TEXT,
    resume_version TEXT,
    cover_letter_version TEXT,
    status TEXT NOT NULL DEFAULT 'Applied', -- 'Applied', 'Interview', 'Rejected', 'Offer'
    applied_date TEXT NOT NULL,
    interview_date TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_company ON applications(company);
