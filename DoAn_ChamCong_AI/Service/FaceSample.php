<?php
declare(strict_types=1);

final class FaceSample
{
    public static function vector(string $bytes): array
    {
        if (strlen($bytes) !== 2048) {
            throw new InvalidArgumentException('Embedding must have 512 float32 values.');
        }
        $values = array_values(unpack('g*', $bytes));
        $norm = 0.0;
        foreach ($values as $value) {
            if (!is_finite($value)) {
                throw new InvalidArgumentException('Embedding contains non-finite values.');
            }
            $norm += $value * $value;
        }
        if (!is_finite($norm) || $norm <= 0) {
            throw new InvalidArgumentException('Embedding has zero or invalid norm.');
        }
        $norm = sqrt($norm);
        return array_map(static fn(float $value): float => $value / $norm, $values);
    }

    public static function requireSameIdentity(string $reference, string $sample): void
    {
        $left = self::vector($reference);
        $right = self::vector($sample);
        $similarity = 0.0;
        foreach ($left as $index => $value) {
            $similarity += $value * $right[$index];
        }
        $configured = getenv('PBL4_ENROLLMENT_THRESHOLD');
        $threshold = $configured === false ? 0.45 : (float)$configured;
        if (!is_finite($threshold) || $threshold <= 0 || $threshold > 1) {
            throw new RuntimeException('Invalid enrollment threshold configuration.');
        }
        if ($similarity < $threshold) {
            throw new InvalidArgumentException('Khuôn mặt không khớp mẫu đầu tiên. Vui lòng đăng ký lại.');
        }
    }
}
