-- Du lieu mau khoi tao cho he thong Cham cong AI (PBL4)
USE `DoAn_ChamCong_AI_MariaDB`;

-- 1. Vai tro
INSERT INTO `VaiTro` (`MaVaiTro`, `TenVaiTro`) VALUES
(1, 'Admin'),
(2, 'Nhân viên')
ON DUPLICATE KEY UPDATE `TenVaiTro`=VALUES(`TenVaiTro`);

-- 2. Thiet bi IoT
INSERT INTO `ThietBi` (`MaTB`, `LoaiTB`, `TrangThai`) VALUES
(1, 'ESP32 Camera & Bio Station', 'Active')
ON DUPLICATE KEY UPDATE `TrangThai`=VALUES(`TrangThai`);

-- 3. Ca lam viec
INSERT INTO `CaLamViec` (`MaCa`, `TenCa`, `GioBatDau`, `GioKetThuc`, `TrangThai`) VALUES
(1, 'Ca Sáng (07:30 - 11:30)', '07:30:00', '11:30:00', 1),
(2, 'Ca Chiều (13:30 - 17:30)', '13:30:00', '17:30:00', 1)
ON DUPLICATE KEY UPDATE `TenCa`=VALUES(`TenCa`);

-- 4. Danh muc bieu hien met moi
INSERT INTO `DanhMucBieuHien` (`MaBieuHien`, `TenBieuHien`, `MoTa`) VALUES
(1, 'Bình thường', 'Tỉnh táo, tập trung làm việc'),
(2, 'Mệt mỏi', 'Lờ đờ, chớp mắt nhiều, thiếu ngủ'),
(3, 'Kiệt sức', 'Sụp mí sâu, ngủ gật, cúi đầu gật gù')
ON DUPLICATE KEY UPDATE `TenBieuHien`=VALUES(`TenBieuHien`);

-- 5. Loai canh bao
INSERT INTO `LoaiCanhBao` (`MaLoaiCB`, `TenLoaiCB`) VALUES
(1, 'Cảnh báo sức khỏe'),
(2, 'Cảnh báo ngủ gật')
ON DUPLICATE KEY UPDATE `TenLoaiCB`=VALUES(`TenLoaiCB`);

-- Administrator accounts are created explicitly with tools/create_admin.php.
-- No default password; rerunning this seed never changes existing accounts.
