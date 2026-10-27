<?php
declare(strict_types=1);

final class InternalApi
{
    public static function requireAuthorized(): bool
    {
        header('Cache-Control: private, no-store');
        $expected = getenv('PBL4_INTERNAL_TOKEN') ?: '';
        $header = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
        if ($expected === '') {
            http_response_code(503);
            header('Content-Type: application/json; charset=utf-8');
            echo json_encode(['success' => false, 'status' => 'error', 'message' => 'Internal API is not configured.']);
            return false;
        }
        if (!is_string($header) || !preg_match('/^Bearer ([^\r\n]+)$/D', $header, $match)
            || !hash_equals($expected, $match[1])) {
            http_response_code(401);
            header('Content-Type: application/json; charset=utf-8');
            header('WWW-Authenticate: Bearer');
            echo json_encode(['success' => false, 'status' => 'error', 'message' => 'Unauthorized.']);
            return false;
        }
        return true;
    }
}
