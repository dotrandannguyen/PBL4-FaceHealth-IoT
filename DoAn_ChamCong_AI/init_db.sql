-- ==========================================================
-- DoAn_ChamCong_AI — Script khởi tạo / đồng bộ schema
-- ==========================================================
-- Server  : localhost (Trusted_Connection=yes)
-- Database: DoAn_ChamCong_AI
-- Driver  : ODBC Driver 17 for SQL Server
--
-- IDEMPOTENT: Chạy lại an toàn, KHÔNG DROP bảng,
-- KHÔNG DELETE dữ liệu, KHÔNG thay đổi dữ liệu cũ.
--
-- Thứ tự tạo tuân theo phụ thuộc FK:
--   VaiTro → NhanVien
--   NhanVien → TaiKhoan, LichSuSucKhoe, LichSuTrangThai, CanhBao,
--              ChamCong, PhanCaNhanVien
--   ThietBi → CanhBao, ChamCong
--   CaLamViec → PhanCaNhanVien, ChamCong
--   DanhMucBieuHien → LichSuTrangThai
--   LoaiCanhBao → CanhBao
--   LichSuTrangThai → CanhBao (MaTT)
-- ==========================================================

USE DoAn_ChamCong_AI;
GO

-- ==========================================================
-- 1. VaiTro
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'VaiTro'
)
BEGIN
    CREATE TABLE VaiTro (
        MaVaiTro  INT            IDENTITY(1,1) PRIMARY KEY,
        TenVaiTro NVARCHAR(100)  NOT NULL
    );
    PRINT N'[OK] Tao bang VaiTro';
END
ELSE
    PRINT N'[SKIP] VaiTro da ton tai';
GO

-- ==========================================================
-- 2. NhanVien
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'NhanVien'
)
BEGIN
    CREATE TABLE NhanVien (
        MaNV          INT              IDENTITY(1,1) PRIMARY KEY,
        HoTen         NVARCHAR(150)    NOT NULL,
        AnhKhuonMat   NVARCHAR(MAX)    NULL,
        MaVaiTro      INT              NULL,
        CONSTRAINT FK_NhanVien_VaiTro
            FOREIGN KEY (MaVaiTro) REFERENCES VaiTro(MaVaiTro)
    );
    PRINT N'[OK] Tao bang NhanVien';
END
ELSE
BEGIN
    -- Bổ sung AnhKhuonMat nếu chưa có (idempotent)
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'NhanVien' AND COLUMN_NAME = 'AnhKhuonMat'
    )
    BEGIN
        ALTER TABLE NhanVien ADD AnhKhuonMat NVARCHAR(MAX) NULL;
        PRINT N'[OK] Them cot AnhKhuonMat vao NhanVien';
    END
    -- Bổ sung MaVaiTro nếu chưa có
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'NhanVien' AND COLUMN_NAME = 'MaVaiTro'
    )
    BEGIN
        ALTER TABLE NhanVien ADD MaVaiTro INT NULL;
        ALTER TABLE NhanVien ADD CONSTRAINT FK_NhanVien_VaiTro
            FOREIGN KEY (MaVaiTro) REFERENCES VaiTro(MaVaiTro);
        PRINT N'[OK] Them cot MaVaiTro vao NhanVien';
    END
    ELSE
        PRINT N'[SKIP] NhanVien da ton tai';
END
GO

-- ==========================================================
-- 3. TaiKhoan
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'TaiKhoan'
)
BEGIN
    CREATE TABLE TaiKhoan (
        MaTK        INT           IDENTITY(1,1) PRIMARY KEY,
        MaNV        INT           NOT NULL,
        TenDangNhap VARCHAR(50)   NOT NULL UNIQUE,
        MatKhau     VARCHAR(255)  NOT NULL,
        CONSTRAINT FK_TaiKhoan_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    );
    PRINT N'[OK] Tao bang TaiKhoan';
END
ELSE
    PRINT N'[SKIP] TaiKhoan da ton tai';
GO

-- ==========================================================
-- 4. ThietBi
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'ThietBi'
)
BEGIN
    CREATE TABLE ThietBi (
        MaTB      INT            IDENTITY(1,1) PRIMARY KEY,
        LoaiTB    NVARCHAR(200)  NULL,
        TrangThai NVARCHAR(100)  NULL
    );
    -- Thiết bị mặc định MaTB=1
    SET IDENTITY_INSERT ThietBi ON;
    INSERT INTO ThietBi (MaTB, LoaiTB, TrangThai)
    VALUES (1, N'Camera', N'Hoat dong');
    SET IDENTITY_INSERT ThietBi OFF;
    PRINT N'[OK] Tao bang ThietBi + du lieu mac dinh';
END
ELSE
BEGIN
    -- Bổ sung LoaiTB nếu chưa có
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'ThietBi' AND COLUMN_NAME = 'LoaiTB'
    )
    BEGIN
        ALTER TABLE ThietBi ADD LoaiTB NVARCHAR(200) NULL;
        PRINT N'[OK] Them cot LoaiTB vao ThietBi';
    END
    -- Bổ sung TrangThai nếu chưa có
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'ThietBi' AND COLUMN_NAME = 'TrangThai'
    )
    BEGIN
        ALTER TABLE ThietBi ADD TrangThai NVARCHAR(100) NULL;
        PRINT N'[OK] Them cot TrangThai vao ThietBi';
    END
    ELSE
        PRINT N'[SKIP] ThietBi da ton tai';
END
GO

-- ==========================================================
-- 5. LichSuSucKhoe
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'LichSuSucKhoe'
)
BEGIN
    CREATE TABLE LichSuSucKhoe (
        MaSK     INT      IDENTITY(1,1) PRIMARY KEY,
        MaNV     INT      NOT NULL,
        NhipTim  INT      NULL,
        SpO2     FLOAT    NULL,
        ThoiGian DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_SucKhoe_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    );
    PRINT N'[OK] Tao bang LichSuSucKhoe';
END
ELSE
    PRINT N'[SKIP] LichSuSucKhoe da ton tai';
GO

-- ==========================================================
-- 6. DanhMucBieuHien
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'DanhMucBieuHien'
)
BEGIN
    CREATE TABLE DanhMucBieuHien (
        MaBieuHien  INT            IDENTITY(1,1) PRIMARY KEY,
        TenBieuHien NVARCHAR(100)  NOT NULL,
        MoTa        NVARCHAR(255)  NULL
    );
    -- Dữ liệu mặc định khớp với mapping trong database.py
    INSERT INTO DanhMucBieuHien (TenBieuHien, MoTa)
    VALUES
        (N'binh_thuong', N'Nguoi dung o trang thai binh thuong'),  -- 1
        (N'buon_ngu',    N'Phat hien bieu hien buon ngu'),         -- 2
        (N'guc_dau',     N'Phat hien dau guc xuong'),              -- 3
        (N'meo_mieng',   N'Phat hien bieu hien meo mieng');        -- 4
    PRINT N'[OK] Tao bang DanhMucBieuHien + du lieu mac dinh';
END
ELSE
BEGIN
    -- Bổ sung MoTa nếu chưa có
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'DanhMucBieuHien' AND COLUMN_NAME = 'MoTa'
    )
    BEGIN
        ALTER TABLE DanhMucBieuHien ADD MoTa NVARCHAR(255) NULL;
        PRINT N'[OK] Them cot MoTa vao DanhMucBieuHien';
    END
    ELSE
        PRINT N'[SKIP] DanhMucBieuHien da ton tai';
END
GO

-- ==========================================================
-- 7. LichSuTrangThai
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'LichSuTrangThai'
)
BEGIN
    CREATE TABLE LichSuTrangThai (
        MaTT        INT      IDENTITY(1,1) PRIMARY KEY,
        MaNV        INT      NOT NULL,
        MaBieuHien  INT      NOT NULL DEFAULT 1,
        ThoiGian    DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_TrangThai_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV),
        CONSTRAINT FK_TrangThai_BieuHien
            FOREIGN KEY (MaBieuHien) REFERENCES DanhMucBieuHien(MaBieuHien)
    );
    PRINT N'[OK] Tao bang LichSuTrangThai';
END
ELSE
    PRINT N'[SKIP] LichSuTrangThai da ton tai';
GO

-- ==========================================================
-- 8. LoaiCanhBao
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'LoaiCanhBao'
)
BEGIN
    CREATE TABLE LoaiCanhBao (
        MaLoaiCB  INT            IDENTITY(1,1) PRIMARY KEY,
        TenLoaiCB NVARCHAR(100)  NOT NULL
    );
    INSERT INTO LoaiCanhBao (TenLoaiCB)
    VALUES
        (N'Canh bao trang thai AI'),  -- 1
        (N'Canh bao moi truong'),     -- 2
        (N'Canh bao suc khoe');       -- 3
    PRINT N'[OK] Tao bang LoaiCanhBao + du lieu mac dinh';
END
ELSE
    PRINT N'[SKIP] LoaiCanhBao da ton tai';
GO

-- ==========================================================
-- 9. CanhBao
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'CanhBao'
)
BEGIN
    CREATE TABLE CanhBao (
        MaCB      INT            IDENTITY(1,1) PRIMARY KEY,
        MaNV      INT            NOT NULL,
        MaLoaiCB  INT            NOT NULL DEFAULT 1,
        NoiDung   NVARCHAR(255)  NULL,
        ThoiGian  DATETIME       DEFAULT GETDATE(),
        MaTT      INT            NULL,
        MaTB      INT            NULL,
        CONSTRAINT FK_CanhBao_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV),
        CONSTRAINT FK_CanhBao_LoaiCanhBao
            FOREIGN KEY (MaLoaiCB) REFERENCES LoaiCanhBao(MaLoaiCB),
        CONSTRAINT FK_CanhBao_TrangThai
            FOREIGN KEY (MaTT) REFERENCES LichSuTrangThai(MaTT),
        CONSTRAINT FK_CanhBao_ThietBi
            FOREIGN KEY (MaTB) REFERENCES ThietBi(MaTB)
    );
    PRINT N'[OK] Tao bang CanhBao';
END
ELSE
    PRINT N'[SKIP] CanhBao da ton tai';
GO

-- ==========================================================
-- 10. CaLamViec
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'CaLamViec'
)
BEGIN
    CREATE TABLE CaLamViec (
        MaCa       INT            IDENTITY(1,1) PRIMARY KEY,
        TenCa      NVARCHAR(100)  NOT NULL,
        GioBatDau  TIME           NOT NULL,
        GioKetThuc TIME           NOT NULL
    );
    INSERT INTO CaLamViec (TenCa, GioBatDau, GioKetThuc)
    VALUES (N'Ca hanh chinh', '08:00:00', '17:00:00');
    PRINT N'[OK] Tao bang CaLamViec + Ca hanh chinh';
END
ELSE
    PRINT N'[SKIP] CaLamViec da ton tai';
GO

-- ==========================================================
-- 11. PhanCaNhanVien
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'PhanCaNhanVien'
)
BEGIN
    CREATE TABLE PhanCaNhanVien (
        MaPhanCa    INT  IDENTITY(1,1) PRIMARY KEY,
        MaNV        INT  NOT NULL,
        MaCa        INT  NOT NULL,
        NgayLamViec DATE NOT NULL,
        CONSTRAINT FK_PhanCa_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV),
        CONSTRAINT FK_PhanCa_CaLamViec
            FOREIGN KEY (MaCa) REFERENCES CaLamViec(MaCa),
        CONSTRAINT UQ_PhanCa_NV_Ngay
            UNIQUE (MaNV, NgayLamViec)
    );
    PRINT N'[OK] Tao bang PhanCaNhanViec';
END
ELSE
    PRINT N'[SKIP] PhanCaNhanVien da ton tai';
GO

-- ==========================================================
-- 12. ChamCong
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'ChamCong'
)
BEGIN
    CREATE TABLE ChamCong (
        MaCC    INT       IDENTITY(1,1) PRIMARY KEY,
        MaNV    INT       NOT NULL,
        GioVao  DATETIME  NULL,
        GioRa   DATETIME  NULL,
        MaTB    INT       NULL,
        MaCa    INT       NULL,
        CONSTRAINT FK_ChamCong_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV),
        CONSTRAINT FK_ChamCong_ThietBi
            FOREIGN KEY (MaTB) REFERENCES ThietBi(MaTB),
        CONSTRAINT FK_ChamCong_CaLamViec
            FOREIGN KEY (MaCa) REFERENCES CaLamViec(MaCa)
    );
    PRINT N'[OK] Tao bang ChamCong';
END
ELSE
BEGIN
    -- Bổ sung MaCa nếu chưa có (idempotent)
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'ChamCong' AND COLUMN_NAME = 'MaCa'
    )
    BEGIN
        ALTER TABLE ChamCong ADD MaCa INT NULL;
        ALTER TABLE ChamCong ADD CONSTRAINT FK_ChamCong_CaLamViec
            FOREIGN KEY (MaCa) REFERENCES CaLamViec(MaCa);
        PRINT N'[OK] Them cot MaCa vao ChamCong';
    END
    ELSE
        PRINT N'[SKIP] ChamCong da ton tai';
END
GO

-- ==========================================================
-- Hoàn tất
-- ==========================================================
PRINT N'';
PRINT N'========================================';
PRINT N'Hoan tat dong bo schema DoAn_ChamCong_AI';
PRINT N'Server  : localhost';
PRINT N'Database: DoAn_ChamCong_AI';
PRINT N'========================================';
GO
