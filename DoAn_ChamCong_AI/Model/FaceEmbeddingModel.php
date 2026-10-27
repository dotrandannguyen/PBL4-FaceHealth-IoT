<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';
require_once __DIR__ . '/../Service/FaceSample.php';

final class FaceEmbeddingModel
{
    /** Lấy metadata các mẫu khuôn mặt của nhân viên, không tải blob ảnh vào danh sách. */
    public function findByEmployee(int $employeeId): array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT MaEmbedding, MaNV, SoChieu, ThoiGianTao,
                   CASE WHEN AnhKhuonMat IS NULL THEN 0 ELSE 1 END AS HasImage
            FROM FaceEmbedding
            WHERE MaNV = :employee_id
            ORDER BY MaEmbedding
            SQL);
        $statement->execute(['employee_id' => $employeeId]);

        return $statement->fetchAll();
    }

    /** Đọc blob ảnh và chủ sở hữu theo MaEmbedding để controller kiểm tra quyền truy cập. */
    public function findImageById(int $embeddingId): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT MaEmbedding, MaNV, AnhKhuonMat
            FROM FaceEmbedding
            WHERE MaEmbedding = :embedding_id
            SQL);
        $statement->execute(['embedding_id' => $embeddingId]);
        $row = $statement->fetch();

        return $row === false ? null : $row;
    }

    /** Đếm số embedding hiện lưu của một nhân viên. */
    public function countByEmployee(int $employeeId): int
    {
        $statement = Database::getConnection()->prepare(
            'SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV = :employee_id'
        );
        $statement->execute(['employee_id' => $employeeId]);

        return (int)$statement->fetchColumn();
    }

    /** Xóa toàn bộ embedding của đúng nhân viên trong transaction và trả số row bị xóa. */
    public function deleteByEmployee(int $employeeId): int
    {
        $pdo = Database::getConnection();
        $pdo->beginTransaction();
        try {
            $this->lockEmployee($pdo, $employeeId);
            $statement = $pdo->prepare('DELETE FROM FaceEmbedding WHERE MaNV = :employee_id');
            $statement->execute(['employee_id' => $employeeId]);
            $deleted = $statement->rowCount();
            $pdo->prepare('UPDATE NhanVien SET AnhKhuonMat = NULL WHERE MaNV = :id')->execute(['id' => $employeeId]);
            $pdo->commit();

            return $deleted;
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }

    /** Thay batch 5 pose nguyên tử; batch mới lỗi sẽ rollback và giữ nguyên mẫu cũ. */
    public function replaceByEmployee(int $employeeId, array $samples): array
    {
        $samples = $this->validateSamples($samples);
        $pdo = Database::getConnection();
        $pdo->beginTransaction();
        try {
            $this->lockEmployee($pdo, $employeeId);
            $delete = $pdo->prepare('DELETE FROM FaceEmbedding WHERE MaNV = :employee_id');
            $delete->execute(['employee_id' => $employeeId]);
            $ids = $this->insertSamples($pdo, $employeeId, $samples);
            $mime = (new finfo(FILEINFO_MIME_TYPE))->buffer($samples[0]['image']);
            $avatar = 'data:' . $mime . ';base64,' . base64_encode($samples[0]['image']);
            $pdo->prepare('UPDATE NhanVien SET AnhKhuonMat = :avatar WHERE MaNV = :id')
                ->execute(['avatar' => $avatar, 'id' => $employeeId]);
            $pdo->commit();

            return $ids;
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }

    private function lockEmployee(PDO $pdo, int $employeeId): void
    {
        $statement = $pdo->prepare('SELECT MaNV FROM NhanVien WHERE MaNV = :id FOR UPDATE');
        $statement->execute(['id' => $employeeId]);
        if ($statement->fetchColumn() === false) {
            throw new InvalidArgumentException('Employee does not exist.');
        }
    }

    /** Kiểm tra đủ 5 pose theo thứ tự, vector 512D và ảnh JPEG/PNG hợp lệ trước khi ghi. */
    private function validateSamples(array $samples): array
    {
        $poses = ['frontal', 'left', 'right', 'up', 'down'];
        if (count($samples) !== count($poses)) {
            throw new InvalidArgumentException('Enrollment requires exactly five samples.');
        }

        $samples = array_values($samples);
        foreach ($samples as $index => $sample) {
            $vector = $sample['vector'] ?? null;
            $image = $sample['image'] ?? null;
            if (($sample['pose'] ?? null) !== $poses[$index]
                || !is_string($vector) || strlen($vector) !== 2048
                || !is_string($image) || $image === '') {
                throw new InvalidArgumentException('Each sample must include a 512D vector and an image.');
            }
            FaceSample::vector($vector);
            if ($index > 0) {
                FaceSample::requireSameIdentity($samples[0]['vector'], $vector);
            }
            $mime = (new finfo(FILEINFO_MIME_TYPE))->buffer($image);
            $size = @getimagesizefromstring($image);
            if (!in_array($mime, ['image/jpeg', 'image/png'], true) || $size === false || $size[0] * $size[1] > 16000000) {
                throw new InvalidArgumentException('Sample image must be a valid JPEG or PNG.');
            }
            if (strlen($image) > 5 * 1024 * 1024) {
                throw new InvalidArgumentException('Sample image exceeds the 5 MB limit.');
            }
        }

        return $samples;
    }

    /** Chèn các cặp ảnh/vector đã validate bằng cùng kết nối transaction. */
    private function insertSamples(PDO $pdo, int $employeeId, array $samples): array
    {
        $statement = $pdo->prepare(<<<'SQL'
            INSERT INTO FaceEmbedding (MaNV, VectorData, AnhKhuonMat, SoChieu, ThoiGianTao)
            VALUES (:employee_id, :vector, :image, 512, CURRENT_TIMESTAMP(3))
            SQL);
        $ids = [];
        foreach ($samples as $sample) {
            $statement->bindValue(':employee_id', $employeeId, PDO::PARAM_INT);
            $statement->bindValue(':vector', $sample['vector'], PDO::PARAM_LOB);
            $statement->bindValue(':image', $sample['image'], PDO::PARAM_LOB);
            $statement->execute();
            $ids[] = (int)$pdo->lastInsertId();
        }

        return $ids;
    }

    /** Đọc gallery cho AI nội bộ và base64 hóa vector chỉ ở ranh giới HTTP/JSON. */
    public function findAllForInternalGallery(): array
    {
        $rows = Database::getConnection()->query(<<<'SQL'
            SELECT fe.MaNV, fe.MaEmbedding, fe.SoChieu, fe.VectorData, nv.HoTen
            FROM FaceEmbedding fe
            LEFT JOIN NhanVien nv ON fe.MaNV = nv.MaNV
            ORDER BY fe.MaNV, fe.MaEmbedding
            SQL)->fetchAll();

        $embeddings = [];
        foreach ($rows as $row) {
            $vector = $row['VectorData'];
            $dimensions = (int)$row['SoChieu'];
            if (!is_string($vector) || $dimensions !== 512 || strlen($vector) !== 2048) {
                throw new RuntimeException('Invalid stored face embedding.');
            }

            $embeddings[] = [
                'ma_nv' => (int)$row['MaNV'],
                'ho_ten' => (string)($row['HoTen'] ?? ('Nhân viên #' . $row['MaNV'])),
                'ma_embedding' => (int)$row['MaEmbedding'],
                'so_chieu' => $dimensions,
                'vector' => base64_encode($vector),
                'sha256' => hash('sha256', $vector),
            ];
        }

        return $embeddings;
    }
}
