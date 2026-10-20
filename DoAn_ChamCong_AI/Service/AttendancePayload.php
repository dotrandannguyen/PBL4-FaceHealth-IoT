<?php
declare(strict_types=1);

final class AttendancePayload
{
    public static function fromArray(array $data): array
    {
        $eventId = $data['event_id'] ?? null;
        if (!is_string($eventId) || !preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/Di', $eventId)) {
            throw new InvalidArgumentException('event_id phải là UUID v4.');
        }
        $ids = [];
        foreach (['MaNV', 'MaTB'] as $key) {
            $value = $data[$key] ?? null;
            if (is_bool($value) || is_array($value)) {
                throw new InvalidArgumentException($key . ' không hợp lệ.');
            }
            $id = filter_var($value, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 2147483647]]);
            if (!is_int($id)) {
                throw new InvalidArgumentException($key . ' không hợp lệ.');
            }
            $ids[$key] = $id;
        }
        $timestamp = $data['occurred_at'] ?? null;
        if (!is_string($timestamp) || !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/D', $timestamp)) {
            throw new InvalidArgumentException('occurred_at phải có ngày giờ và múi giờ.');
        }
        try {
            $occurred = new DateTimeImmutable($timestamp);
            $errors = DateTimeImmutable::getLastErrors();
            if ($errors !== false && ($errors['warning_count'] || $errors['error_count'])) {
                throw new InvalidArgumentException('Ngày giờ không hợp lệ.');
            }
        } catch (Exception $exception) {
            throw new InvalidArgumentException('Ngày giờ không hợp lệ.');
        }
        if ($occurred->getTimestamp() > time() + 300 || (int)$occurred->format('Y') < 2020) {
            throw new InvalidArgumentException('Ngày giờ nằm ngoài phạm vi cho phép.');
        }
        $occurred = $occurred->setTimezone(new DateTimeZone('Asia/Ho_Chi_Minh'));
        $status = $data['TrangThai'] ?? 'Unknown';
        $labels = ['Normal' => 'Bình thường', 'Fatigue' => 'Mệt mỏi', 'Exhausted' => 'Kiệt sức', 'Unknown' => 'Chưa đánh giá'];
        if (!is_string($status) || !isset($labels[$status])) {
            throw new InvalidArgumentException('TrangThai không hợp lệ.');
        }
        $metrics = [];
        foreach (['NhipTim' => 300, 'SpO2' => 100] as $key => $maximum) {
            $value = $data[$key] ?? null;
            if ($value !== null && (!is_int($value) && !is_float($value))) {
                throw new InvalidArgumentException($key . ' phải là số hoặc null.');
            }
            if ($value !== null && (!is_finite((float)$value) || $value <= 0 || $value > $maximum)) {
                throw new InvalidArgumentException($key . ' nằm ngoài phạm vi cho phép.');
            }
            $metrics[$key] = $value;
        }
        // NhipTim is an INT column; reject fractional values instead of silently rounding.
        if ($metrics['NhipTim'] !== null && floor((float)$metrics['NhipTim']) !== (float)$metrics['NhipTim']) {
            throw new InvalidArgumentException('NhipTim phải là số nguyên BPM.');
        }
        if ($metrics['NhipTim'] !== null) {
            $metrics['NhipTim'] = (int)$metrics['NhipTim'];
        }
        $image = null;
        if (isset($data['image'])) {
            if (!is_string($data['image']) || strlen($data['image']) > 7 * 1024 * 1024) {
                throw new InvalidArgumentException('Ảnh quá lớn hoặc không hợp lệ.');
            }
            $image = base64_decode($data['image'], true);
            if (!is_string($image) || strlen($image) > 5 * 1024 * 1024 || $image === '') {
                throw new InvalidArgumentException('Ảnh base64 không hợp lệ.');
            }
            $size = @getimagesizefromstring($image);
            if ($size === false || !in_array($size['mime'], ['image/jpeg', 'image/png'], true)
                || $size[0] * $size[1] > 16000000) {
                throw new InvalidArgumentException('Ảnh phải là JPEG/PNG hợp lệ, tối đa 16 megapixel.');
            }
        }
        $result = $ids + $metrics + [
            'event_id' => strtolower($eventId), 'occurred_at' => $occurred->format('Y-m-d H:i:s.v'),
            'work_date' => $occurred->format('Y-m-d'), 'raw_status' => $status,
            'status_label' => $labels[$status], 'image' => $image,
        ];
        $hashData = $result;
        $hashData['image'] = $image === null ? null : hash('sha256', $image);
        $result['request_hash'] = hash('sha256', json_encode($hashData, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE));
        return $result;
    }
}
