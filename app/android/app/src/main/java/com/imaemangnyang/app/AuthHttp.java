// app/android/app/src/main/java/com/imaemangnyang/app/AuthHttp.java
// 인증 서버의 앱의 길(/api/v1/auth/app/...)을 부르는 네이티브의 HTTP(#429).
// WebView 를 거치지 않아 Origin 머리말이 붙지 않는다. 인증 서버는 Origin 이 붙은 요청을 브라우저로 보고 거절한다.
// 서버에 닿지 못하면 IOException 을 던진다. 상태 코드가 있는 답(4xx, 5xx 포함)은 그대로 돌려준다.

package com.imaemangnyang.app;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.json.JSONException;
import org.json.JSONObject;

final class AuthHttp {

    private static final int TIMEOUT_MILLIS = 15_000;

    /** 서버의 답. body 는 JSON 이 아니거나 비었으면 null 이다 */
    static final class Answer {

        final int status;
        final JSONObject body;

        Answer(int status, JSONObject body) {
            this.status = status;
            this.body = body;
        }
    }

    private final String apiOrigin;

    AuthHttp(String apiOrigin) {
        this.apiOrigin = apiOrigin;
    }

    /** POST 한다. accessToken 이 있으면 Authorization 에 싣는다 */
    Answer post(String path, JSONObject body, String accessToken) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) URI.create(apiOrigin + path).toURL().openConnection();
        try {
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(TIMEOUT_MILLIS);
            connection.setReadTimeout(TIMEOUT_MILLIS);
            connection.setUseCaches(false);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setRequestProperty("Accept", "application/json");
            if (accessToken != null) connection.setRequestProperty("Authorization", "Bearer " + accessToken);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(body.toString().getBytes(StandardCharsets.UTF_8));
            }
            int status = connection.getResponseCode();
            return new Answer(status, parse(readBody(connection, status)));
        } finally {
            connection.disconnect();
        }
    }

    private static String readBody(HttpURLConnection connection, int status) throws IOException {
        InputStream stream = status >= 400 ? connection.getErrorStream() : connection.getInputStream();
        if (stream == null) return "";
        try (InputStream input = stream; ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096];
            int read;
            while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
            return output.toString("UTF-8");
        }
    }

    private static JSONObject parse(String text) {
        if (text.isEmpty()) return null;
        try {
            return new JSONObject(text);
        } catch (JSONException exception) {
            return null;
        }
    }
}
