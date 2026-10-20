-- Back up the existing database before applying. Safe to re-run on MariaDB.
ALTER TABLE ChamCong
    ADD COLUMN IF NOT EXISTS TheTrang VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS TheTrangVao VARCHAR(100) NULL,
    ADD COLUMN IF NOT EXISTS TheTrangRa VARCHAR(100) NULL;
ALTER TABLE LichSuSucKhoe
    ADD COLUMN IF NOT EXISTS TheTrang VARCHAR(100) NULL;

CREATE TABLE IF NOT EXISTS AttendanceEvent (
    EventId CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    RequestHash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    MaNV INT NOT NULL,
    MaTB INT NOT NULL,
    OccurredAt DATETIME(3) NOT NULL,
    ResultJson LONGTEXT NULL,
    CreatedAt DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (EventId),
    KEY IX_AttendanceEvent_MaNV_OccurredAt (MaNV, OccurredAt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
