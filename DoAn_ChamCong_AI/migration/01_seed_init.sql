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

-- 6. Nhan vien quan tri mau (MaNV = 1)
INSERT INTO `NhanVien` (`MaNV`, `HoTen`, `AnhKhuonMat`, `MaVaiTro`) VALUES
(1, 'Quản Trị Viên Hệ Thống', NULL, 1)
ON DUPLICATE KEY UPDATE `HoTen`=VALUES(`HoTen`);

-- 7. Tai khoan quan tri: username: admin / password: password123 (hoac 123456)
-- Hash bcrypt tieu chuan cho mat khau '123456':
INSERT INTO `TaiKhoan` (`MaTK`, `MaNV`, `TenDangNhap`, `MatKhau`) VALUES
(1, 1, 'admin', '$2y$10$ZcKps/RyxchOdXfZsSnQf.UsaiGZwk4L7TmtCON4sxWFZArP29dKW')
ON DUPLICATE KEY UPDATE `TenDangNhap`=VALUES(`TenDangNhap`), `MatKhau`=VALUES(`MatKhau`);
