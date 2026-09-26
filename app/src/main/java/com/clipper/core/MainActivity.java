package com.clipper.core;

import android.Manifest;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

public class MainActivity extends Activity {

    private static final String CHANNEL_ID = "clipper_core_notifications";
    private static final int NOTIFICATION_ID = 1001;
    private static final int REQUEST_CODE_PICK_SRT = 2001;

    private EditText etUrl;
    private View layoutFileSelected;
    private TextView tvSelectedFileName;
    private Button btnRemoveFile;
    private Button btnPickFile;
    private Button btnSample;
    private Button btnAnalyze;
    private Button btnClear;
    private ProgressBar pbLoading;

    private String selectedSrtContent = null;
    private String selectedFileName = null;

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

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    "Clipper Core Status",
                    NotificationManager.IMPORTANCE_DEFAULT
            );
            channel.setDescription("Notifikasi status proses dan hasil Clipper Core");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private void sendNotification(String title, String message, boolean isOngoing) {
        try {
            Notification.Builder builder;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                builder = new Notification.Builder(this, CHANNEL_ID);
            } else {
                builder = new Notification.Builder(this);
            }

            Intent intent = new Intent(this, MainActivity.class);
            intent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                flags |= PendingIntent.FLAG_IMMUTABLE;
            }
            PendingIntent pendingIntent = PendingIntent.getActivity(this, 0, intent, flags);

            builder.setSmallIcon(R.mipmap.ic_launcher)
                    .setContentTitle(title)
                    .setContentText(message)
                    .setStyle(new Notification.BigTextStyle().bigText(message))
                    .setContentIntent(pendingIntent)
                    .setOngoing(isOngoing)
                    .setAutoCancel(!isOngoing);

            NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (manager != null) {
                manager.notify(NOTIFICATION_ID, builder.build());
            }
        } catch (Exception ignored) {
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
            String sourceUrl
    ) {
        runOnUiThread(() -> {
            pbLoading.setVisibility(View.VISIBLE);
            btnAnalyze.setEnabled(false);
            btnAnalyze.setText("Memproses...");
        });

        sendNotification("Clipper Core", "Menganalisis transcript dan menyusun prompt...", true);

        new Thread(() -> {
            try {
                Python python = Python.getInstance();
                PyObject module = python.getModule("prefilter");

                PyObject candidates =
                        module.callAttr("find_candidates", transcript);

                PyObject prompt =
                        module.callAttr(
                                "build_gemini_prompt",
                                candidates,
                                sourceUrl
                        );

                savePromptToDownload(prompt.toJava(String.class));

                runOnUiThread(() -> {
                    pbLoading.setVisibility(View.GONE);
                    btnAnalyze.setEnabled(true);
                    btnAnalyze.setText("Analisis Transcript");
                    Toast.makeText(MainActivity.this, "Prompt selesai disimpan di Download/ClipperCore.", Toast.LENGTH_LONG).show();
                });

                sendNotification(
                        "Clipper Core: Prompt Selesai",
                        "Prompt validator telah disimpan di folder Download/ClipperCore/prompt.txt",
                        false
                );
            } catch (Exception e) {
                runOnUiThread(() -> {
                    pbLoading.setVisibility(View.GONE);
                    btnAnalyze.setEnabled(true);
                    btnAnalyze.setText("Analisis Transcript");
                    Toast.makeText(MainActivity.this, "Gagal memproses transcript. Cek notifikasi.", Toast.LENGTH_SHORT).show();
                });

                sendNotification(
                        "Clipper Core: Gagal",
                        e.getMessage() != null ? e.getMessage() : "Terjadi kesalahan tidak terduga saat memproses transcript.",
                        false
                );
            }
        }).start();
    }

    private String getFileName(Uri uri) {
        String result = null;
        if ("content".equals(uri.getScheme())) {
            try (Cursor cursor = getContentResolver().query(
                    uri,
                    new String[]{OpenableColumns.DISPLAY_NAME},
                    null,
                    null,
                    null
            )) {
                if (cursor != null && cursor.moveToFirst()) {
                    int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                    if (index != -1) {
                        result = cursor.getString(index);
                    }
                }
            } catch (Exception ignored) {
            }
        }
        if (result == null) {
            result = uri.getPath();
            if (result != null) {
                int cut = result.lastIndexOf('/');
                if (cut != -1) {
                    result = result.substring(cut + 1);
                }
            }
        }
        return result;
    }

    private void updateSelectedFileUI() {
        if (selectedSrtContent != null && !selectedSrtContent.trim().isEmpty()) {
            tvSelectedFileName.setText(selectedFileName != null ? selectedFileName : "transcript.srt");
            layoutFileSelected.setVisibility(View.VISIBLE);
            btnPickFile.setText("📁 Ganti File SRT");
        } else {
            selectedSrtContent = null;
            selectedFileName = null;
            layoutFileSelected.setVisibility(View.GONE);
            btnPickFile.setText("📁 Pilih File SRT dari HP");
        }
    }

    private void loadSrtFromUri(Uri uri) {
        try {
            String name = getFileName(uri);
            try (InputStream in = getContentResolver().openInputStream(uri);
                 ByteArrayOutputStream buffer = new ByteArrayOutputStream()) {
                if (in == null) {
                    Toast.makeText(this, "Tidak dapat membaca file.", Toast.LENGTH_SHORT).show();
                    return;
                }
                byte[] data = new byte[8192];
                int count;
                while ((count = in.read(data)) != -1) {
                    buffer.write(data, 0, count);
                }
                selectedSrtContent = buffer.toString("UTF-8");
                selectedFileName = (name != null && !name.trim().isEmpty()) ? name : "transcript.srt";
            }

            updateSelectedFileUI();
            Toast.makeText(this, "File SRT berhasil dimuat: " + selectedFileName, Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            Toast.makeText(this, "Gagal memuat file: " + e.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }

    private void openFilePicker() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                "text/*",
                "application/x-subrip",
                "application/octet-stream"
        });
        try {
            startActivityForResult(intent, REQUEST_CODE_PICK_SRT);
        } catch (Exception e) {
            Intent fallback = new Intent(Intent.ACTION_GET_CONTENT);
            fallback.setType("*/*");
            try {
                startActivityForResult(fallback, REQUEST_CODE_PICK_SRT);
            } catch (Exception ex) {
                Toast.makeText(this, "Tidak ada aplikasi pemilih file yang tersedia.", Toast.LENGTH_SHORT).show();
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_CODE_PICK_SRT && resultCode == RESULT_OK && data != null) {
            Uri uri = data.getData();
            if (uri != null) {
                loadSrtFromUri(uri);
            }
        }
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);

        createNotificationChannel();

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 101);
            }
        }

        if (!Python.isStarted()) {
            Python.start(new com.chaquo.python.android.AndroidPlatform(this));
        }

        setContentView(R.layout.activity_main);

        etUrl = findViewById(R.id.et_youtube_url);
        layoutFileSelected = findViewById(R.id.layout_file_selected);
        tvSelectedFileName = findViewById(R.id.tv_selected_file_name);
        btnRemoveFile = findViewById(R.id.btn_remove_file);
        btnPickFile = findViewById(R.id.btn_pick_file);
        btnSample = findViewById(R.id.btn_sample_srt);
        btnAnalyze = findViewById(R.id.btn_analyze);
        btnClear = findViewById(R.id.btn_clear);
        pbLoading = findViewById(R.id.pb_loading);

        btnPickFile.setOnClickListener(v -> openFilePicker());

        btnRemoveFile.setOnClickListener(v -> {
            selectedSrtContent = null;
            selectedFileName = null;
            updateSelectedFileUI();
            Toast.makeText(this, "File SRT dilepas.", Toast.LENGTH_SHORT).show();
        });

        btnSample.setOnClickListener(v -> {
            selectedSrtContent =
                    "1\n00:00:01,000 --> 00:00:04,500\nSelamat datang di podcast Clipper Core episode perdana.\n\n"
                            + "2\n00:00:05,000 --> 00:00:09,200\nHari ini kita membahas rahasia sukses membuat konten video pendek viral.\n\n"
                            + "3\n00:00:10,000 --> 00:00:14,800\nKunci utamanya adalah hook di tiga detik pertama yang menarik perhatian audiens.\n\n"
                            + "4\n00:00:15,000 --> 00:00:19,500\nSetelah itu sampaikan pesan inti dengan padat dan hilangkan kata-kata yang bertele-tele.\n\n"
                            + "5\n00:00:20,000 --> 00:00:24,500\nAkhiri dengan call to action yang jelas agar audiens terdorong berkomentar dan membagikan video.";
            selectedFileName = "contoh_podcast.srt";
            updateSelectedFileUI();
            Toast.makeText(this, "Contoh file SRT berhasil dimuat.", Toast.LENGTH_SHORT).show();
        });

        btnClear.setOnClickListener(v -> {
            etUrl.setText("");
            selectedSrtContent = null;
            selectedFileName = null;
            updateSelectedFileUI();
            pbLoading.setVisibility(View.GONE);
            btnAnalyze.setEnabled(true);
            btnAnalyze.setText("Analisis Transcript");
        });

        btnAnalyze.setOnClickListener(v -> {
            String value = etUrl.getText().toString().replaceAll("\\s+", "");

            if (selectedSrtContent != null && !selectedSrtContent.trim().isEmpty()) {
                runPrefilter(selectedSrtContent, value);
                return;
            }

            if (value.isEmpty()) {
                Toast.makeText(this, "Pilih file SRT dari HP atau masukkan URL YouTube", Toast.LENGTH_SHORT).show();
                return;
            }

            pbLoading.setVisibility(View.VISIBLE);
            btnAnalyze.setEnabled(false);
            btnAnalyze.setText("Memproses...");
            sendNotification("Clipper Core", "Mengunduh transcript video YouTube...", true);

            new Thread(() -> {
                try {
                    String cached = readTranscriptCache(value);

                    if (cached != null && !cached.trim().isEmpty()) {
                        runOnUiThread(() ->
                                runPrefilter(cached, value)
                        );
                        return;
                    }

                    Python python = Python.getInstance();
                    PyObject module = python.getModule("main");

                    String result =
                            module.callAttr("transcript_srt", value)
                                    .toJava(String.class);

                    writeTranscriptCache(value, result);

                    runOnUiThread(() ->
                            runPrefilter(result, value)
                    );
                } catch (Exception e) {
                    runOnUiThread(() -> {
                        pbLoading.setVisibility(View.GONE);
                        btnAnalyze.setEnabled(true);
                        btnAnalyze.setText("Analisis Transcript");
                        Toast.makeText(MainActivity.this, "Gagal mengunduh transcript. Cek notifikasi.", Toast.LENGTH_SHORT).show();
                    });

                    sendNotification(
                            "Gagal Mengambil Transcript",
                            e.getMessage() != null ? e.getMessage() : "Tidak dapat mengambil transcript dari URL yang diberikan.",
                            false
                    );
                }
            }).start();
        });
    }
}
