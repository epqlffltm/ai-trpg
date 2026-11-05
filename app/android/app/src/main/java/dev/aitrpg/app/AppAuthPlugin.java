// app/android/app/src/main/java/dev/aitrpg/app/AppAuthPlugin.java
// 화면이 부르는 AppAuth 플러그인(#429). refresh 토큰은 이 플러그인만 쥐고, 화면에는 access 토큰만 넘긴다.
// 화면 쪽의 약속은 web/apps/web/src/api/appAuth.ts 의 머리에 있다. 이 파일이 그 약속을 지킨다.
//
//   - 메서드마다 { status, body } 로 답한다. status 는 인증 서버의 상태 코드, body 는 그 본문이다
//   - 토큰을 주는 답(200)에서 refresh_token 을 꺼내 RefreshTokenStore 에 두고, body 에서는 refresh_token 과 refresh_expires_in 을 뺀다
//   - 서버에 닿지 못하면 reject 한다(화면은 NetworkError 로 본다)
//   - 갱신은 둔 토큰이 없으면 서버를 부르지 않고 { status: 401 } 이다. 갱신과 로그아웃이 401 이면 둔 토큰을 지운다
//   - 모든 일을 한 줄의 작업자(단일 스레드)로 차례로 한다. 갱신이 둘 겹쳐 가면 인증 서버가 재사용으로 보고 모든 세션을 끊는다
//
// API 의 출처는 capacitor.config.ts 의 plugins.AppAuth.apiOrigin 이다(APP_API_ORIGIN).

package dev.aitrpg.app;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.IOException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONException;
import org.json.JSONObject;

@CapacitorPlugin(name = "AppAuth")
public class AppAuthPlugin extends Plugin {

    private static final String LOGIN_VERIFY = "/api/v1/auth/app/login/verify";
    private static final String REFRESH = "/api/v1/auth/app/refresh";
    private static final String LOGOUT = "/api/v1/auth/app/logout";
    private static final String PASSWORD_CHANGE = "/api/v1/auth/app/password/change";
    private static final String REFRESH_TOKEN = "refresh_token";
    private static final String REFRESH_EXPIRES_IN = "refresh_expires_in";
    private static final int UNAUTHORIZED = 401;
    private static final int OK = 200;

    /** 한 번에 하나씩. 갱신이 겹치지 않는다 */
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private RefreshTokenStore store;
    private AuthHttp http;

    @Override
    public void load() {
        store = new RefreshTokenStore(getContext());
        http = new AuthHttp(getConfig().getString("apiOrigin", ""));
    }

    @PluginMethod
    public void verifyLogin(PluginCall call) {
        String loginTicket = call.getString("loginTicket");
        String code = call.getString("code");
        if (loginTicket == null || code == null) {
            call.reject("loginTicket 과 code 가 필요하다");
            return;
        }
        worker.execute(() -> {
            try {
                JSONObject body = new JSONObject().put("login_ticket", loginTicket).put("code", code);
                call.resolve(keepTokenAndAnswer(http.post(LOGIN_VERIFY, body, null)));
            } catch (IOException | JSONException exception) {
                call.reject("서버에 닿지 못했다", exception);
            }
        });
    }

    @PluginMethod
    public void refresh(PluginCall call) {
        worker.execute(() -> {
            String token = store.read();
            if (token == null) {
                call.resolve(answer(UNAUTHORIZED, null));
                return;
            }
            try {
                AuthHttp.Answer answer = http.post(REFRESH, new JSONObject().put(REFRESH_TOKEN, token), null);
                if (answer.status == UNAUTHORIZED) store.clear();
                call.resolve(keepTokenAndAnswer(answer));
            } catch (IOException | JSONException exception) {
                call.reject("서버에 닿지 못했다", exception);
            }
        });
    }

    @PluginMethod
    public void logout(PluginCall call) {
        worker.execute(() -> {
            String token = store.read();
            // 서버에 닿든 못 닿든 이 기기의 토큰은 지운다. 화면도 상태를 비운다
            store.clear();
            if (token == null) {
                call.resolve(answer(204, null));
                return;
            }
            try {
                AuthHttp.Answer answer = http.post(LOGOUT, new JSONObject().put(REFRESH_TOKEN, token), null);
                call.resolve(answer(answer.status, answer.body));
            } catch (IOException | JSONException exception) {
                call.reject("서버에 닿지 못했다", exception);
            }
        });
    }

    @PluginMethod
    public void changePassword(PluginCall call) {
        String accessToken = call.getString("accessToken");
        String currentPassword = call.getString("currentPassword");
        String newPassword = call.getString("newPassword");
        if (accessToken == null || currentPassword == null || newPassword == null) {
            call.reject("accessToken, currentPassword, newPassword 가 필요하다");
            return;
        }
        worker.execute(() -> {
            try {
                JSONObject body = new JSONObject()
                    .put("current_password", currentPassword)
                    .put("new_password", newPassword);
                call.resolve(keepTokenAndAnswer(http.post(PASSWORD_CHANGE, body, accessToken)));
            } catch (IOException | JSONException exception) {
                call.reject("서버에 닿지 못했다", exception);
            }
        });
    }

    /** 토큰을 주는 답이면 refresh 토큰을 두고 본문에서 뺀다. 화면에 넘길 답을 만든다 */
    private JSObject keepTokenAndAnswer(AuthHttp.Answer answer) {
        JSONObject body = answer.body;
        if (answer.status == OK && body != null) {
            String token = body.optString(REFRESH_TOKEN, "");
            if (!token.isEmpty()) store.write(token);
            body.remove(REFRESH_TOKEN);
            body.remove(REFRESH_EXPIRES_IN);
        }
        return answer(answer.status, body);
    }

    private static JSObject answer(int status, JSONObject body) {
        JSObject result = new JSObject();
        result.put("status", status);
        if (body != null) result.put("body", body);
        return result;
    }
}
