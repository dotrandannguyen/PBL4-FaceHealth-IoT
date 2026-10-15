-- Run once against DoAn_ChamCong_AI_MariaDB after taking a database backup.
-- Existing shifts receive TrangThai = 1 via the NOT NULL DEFAULT.
ALTER TABLE `CaLamViec`
    ADD COLUMN `TrangThai` TINYINT(1) NOT NULL DEFAULT 1;
