package com.clipper.core;

import android.app.Activity;
import android.content.ContentUris;
import android.content.ContentValues;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

public class MainActivity extends Activity {

    private String transcriptCacheKey(String sourceUrl) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(sourceUrl.trim().getBytes(StandardCharsets.UTF_8));

        StringBuilder hex = new StringBuilder();
        for (byte value : digest) {
            hex.append(String.format("%02x", value));
        }

        return "transcript-" + hex + ".srt";
    }

    private File transcriptCacheFile(String sourceUrl) throws Exception {
        return new File(getCacheDir(), transcriptCacheKey(sourceUrl));
    }

    private String readTranscriptCache(String sourceUrl) throws Exception {
        File cacheFile = transcriptCacheFile(sourceUrl);

        if (!cacheFile.isFile()) {
            return null;
        }

        try (FileInputStream in = new FileInputStream(cacheFile);
             java.io.ByteArrayOutputStream buffer =
                     new java.io.ByteArrayOutputStream()) {

            byte[] data = new byte[8192];
            int count;

            while ((count = in.read(data)) != -1) {
                buffer.write(data, 0, count);
            }

            return buffer.toString("UTF-8");
        }
    }

    private void writeTranscriptCache(
            String sourceUrl,
            String transcript
    ) throws Exception {
        File cacheFile = transcriptCacheFile(sourceUrl);

        try (FileOutputStream out = new FileOutputStream(cacheFile)) {
            out.write(transcript.getBytes(StandardCharsets.UTF_8));
        }
    }

    private void savePromptToDownload(String promptText) throws Exception {
        byte[] data = promptText.getBytes(StandardCharsets.UTF_8);
        boolean saved = false;

        try {
            File downloadDir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
            File clipperDir = new File(downloadDir, "ClipperCore");
            if (!clipperDir.exists()) {
                clipperDir.mkdirs();
            }
            File targetFile = new File(clipperDir, "prompt.txt");
            try (FileOutputStream fos = new FileOutputStream(targetFile)) {
                fos.write(data);
                fos.flush();
            }
            if (targetFile.exists() && targetFile.length() > 0) {
                saved = true;
            }
        } catch (Exception ignored) {
        }

        if (saved) {
            return;
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            String relativePath = Environment.DIRECTORY_DOWNLOADS + "/ClipperCore/";

            Uri[] collections = new Uri[]{
                    MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                    MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY),
                    MediaStore.Files.getContentUri("external"),
                    MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            };

            for (Uri collection : collections) {
                try {
                    try (Cursor cursor = getContentResolver().query(
                            collection,
                            new String[]{MediaStore.MediaColumns._ID},
                            MediaStore.MediaColumns.DISPLAY_NAME + "=? AND ("
                                    + MediaStore.MediaColumns.RELATIVE_PATH + "=? OR "
                                    + MediaStore.MediaColumns.RELATIVE_PATH + "=?)",
                            new String[]{"prompt.txt", relativePath, Environment.DIRECTORY_DOWNLOADS + "/ClipperCore"},
                            null
                    )) {
                        if (cursor != null && cursor.moveToFirst()) {
                            long id = cursor.getLong(cursor.getColumnIndexOrThrow(MediaStore.MediaColumns._ID));
                            Uri existingUri = ContentUris.withAppendedId(collection, id);
                            try {
                                getContentResolver().delete(existingUri, null, null);
                            } catch (Exception ignored) {
                            }
                        }
                    } catch (Exception ignored) {
                    }

                    ContentValues values = new ContentValues();
                    values.put(MediaStore.MediaColumns.DISPLAY_NAME, "prompt.txt");
                    values.put(MediaStore.MediaColumns.MIME_TYPE, "text/plain");
                    values.put(MediaStore.MediaColumns.RELATIVE_PATH, relativePath);
                    values.put(MediaStore.MediaColumns.IS_PENDING, 1);

                    Uri outputUri = getContentResolver().insert(collection, values);
                    if (outputUri != null) {
                        try (OutputStream out = getContentResolver().openOutputStream(outputUri)) {
                            if (out != null) {
                                out.write(data);
                                out.flush();
                            }
                        }

                        ContentValues ready = new ContentValues();
                        ready.put(MediaStore.MediaColumns.IS_PENDING, 0);
                        getContentResolver().update(outputUri, ready, null, null);
                        saved = true;
                        break;
                    }
                } catch (Exception ignored) {
                }
            }
        }

        if (!saved) {
            throw new IllegalStateException("Gagal membuat prompt.txt di Download.");
        }
    }

    private void runPrefilter(
            String transcript,
            String sourceUrl,
            TextView status,
            Button button
    ) {
        runOnUiThread(() -> {
            button.setEnabled(false);
            status.setText("PREFILTER: menganalisis transcript...");
        });

        new Thread(() -> {
            try {
                Python python = Python.getInstance();
                PyObject module = python.getModule("prefilter");

                PyObject candidates =
                        module.callAttr("find_candidates", transcript);

                runOnUiThread(() ->
                        status.setText("PREFILTER: menyusun prompt Gemini...")
                );

                PyObject prompt =
                        module.callAttr(
                                "build_gemini_prompt",
                                candidates,
                                sourceUrl
                        );

                savePromptToDownload(prompt.toJava(String.class));

                int count = candidates.asList().size();

                runOnUiThread(() -> {
                    button.setEnabled(true);
                    status.setText(
                            "PREFILTER selesai: " + count
                                    + " kandidat.\n"
                                    + "Prompt: Download/ClipperCore/prompt.txt"
                    );
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    button.setEnabled(true);
                    status.setText(
                            "PREFILTER gagal: " + e.getMessage()
                    );
                });
            }
        }).start();
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);

        if (!Python.isStarted()) {
            Python.start(new com.chaquo.python.android.AndroidPlatform(this));
        }

        ScrollView scrollView = new ScrollView(this);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(32, 32, 32, 32);

        TextView title = new TextView(this);
        title.setText("Clipper Core");
        title.setTextSize(24);

        EditText url = new EditText(this);
        url.setHint("YouTube Podcast URL");

        EditText transcript = new EditText(this);
        transcript.setHint("Tempel transcript SRT");
        transcript.setGravity(android.view.Gravity.TOP);
        transcript.setMinLines(8);
        transcript.setInputType(android.text.InputType.TYPE_CLASS_TEXT
                | android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);

        Button button = new Button(this);
        button.setText("Analisis Transcript");

        TextView status = new TextView(this);
        status.setText("Siap.");

        button.setOnClickListener(v -> {
            String srt = transcript.getText().toString().trim();
            String value = url.getText().toString().trim();

            if (!srt.isEmpty()) {
                runPrefilter(srt, value, status, button);
                return;
            }

            if (value.isEmpty()) {
                status.setText("Masukkan URL YouTube atau transcript SRT.");
                return;
            }

            button.setEnabled(false);

            new Thread(() -> {
                try {
                    String cached = readTranscriptCache(value);

                    if (cached != null && !cached.trim().isEmpty()) {
                        runOnUiThread(() -> {
                            status.setText(
                                    "Transcript dari cache. Menjalankan PREFILTER..."
                            );
                            runPrefilter(cached, value, status, button);
                        });
                        return;
                    }

                    runOnUiThread(() ->
                            status.setText("Mengambil transcript YouTube...")
                    );

                    Python python = Python.getInstance();
                    PyObject module = python.getModule("main");

                    String result =
                            module.callAttr("transcript_srt", value)
                                    .toJava(String.class);

                    writeTranscriptCache(value, result);

                    runOnUiThread(() ->
                            runPrefilter(result, value, status, button)
                    );
                } catch (Exception e) {
                    runOnUiThread(() -> {
                        button.setEnabled(true);
                        status.setText(
                                "Transcript gagal diambil: " + e.getMessage()
                        );
                    });
                }
            }).start();
        });

        layout.addView(title);
        layout.addView(url);
        layout.addView(transcript);
        layout.addView(button);
        layout.addView(status);

        scrollView.addView(layout);
        setContentView(scrollView);
    }
}
