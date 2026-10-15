<?php
declare(strict_types=1);

final class Database
{
    private static ?PDO $connection = null;

    /** Tạo hoặc trả về kết nối PDO dùng chung tới MariaDB của ứng dụng PHP. */
    public static function getConnection(): PDO
    {
        if (self::$connection !== null) {
            return self::$connection;
        }

        if (!in_array('mysql', PDO::getAvailableDrivers(), true)) {
            throw new RuntimeException('The PDO MySQL driver is not enabled.');
        }

        $host = getenv('MARIADB_HOST') ?: '127.0.0.1';
        $port = getenv('MARIADB_PORT') ?: '3306';
        $database = getenv('MARIADB_DATABASE') ?: 'DoAn_ChamCong_AI_MariaDB';
        $username = getenv('MARIADB_USER') ?: 'root';
        $password = getenv('MARIADB_PASSWORD');
        if ($password === false) {
            $password = '';
        }

        $dsn = sprintf(
            'mysql:host=%s;port=%s;dbname=%s;charset=utf8mb4',
            $host,
            $port,
            $database
        );

        self::$connection = new PDO($dsn, $username, $password, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);

        return self::$connection;
    }
}
