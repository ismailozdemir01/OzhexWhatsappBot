package com.ozhex.whatsapp

import android.app.Activity
import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.widget.*

class MainActivity : Activity() {
    private lateinit var api: EditText
    private lateinit var token: EditText
    private lateinit var consent: CheckBox
    private lateinit var status: TextView
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs=getSharedPreferences("ozhex",MODE_PRIVATE)
        val root=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;setPadding(32,48,32,32) }
        root.addView(TextView(this).apply { text="Ozhex WhatsApp Activity";textSize=22f })
        api=EditText(this).apply { hint="Backend URL";setText(prefs.getString("api_url","http://10.0.2.2:8000")) }
        token=EditText(this).apply { hint="Access token";setText(prefs.getString("access_token",""));inputType= android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD }
        consent=CheckBox(this).apply { text="Bu cihazdaki WhatsApp kullanım geçişlerinin hesabıma gönderilmesine açık rıza veriyorum.";isChecked=prefs.getBoolean("consent",false) }
        status=TextView(this)
        val permission=Button(this).apply { text="Usage Access ayarları";setOnClickListener { startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)) } }
        val start=Button(this).apply { text="Kaydet ve izlemeyi başlat";setOnClickListener { saveAndStart() } }
        val stop=Button(this).apply { text="İzlemeyi durdur ve rızayı kapat";setOnClickListener { prefs.edit().putBoolean("consent",false).apply();stopService(Intent(this@MainActivity,UsageMonitorService::class.java));consent.isChecked=false;status.text="İzleme ve rıza kapatıldı." } }
        root.addView(api);root.addView(token);root.addView(consent);root.addView(permission);root.addView(start);root.addView(stop);root.addView(status)
        setContentView(ScrollView(this).apply { addView(root) })
    }
    private fun hasUsageAccess():Boolean {
        val ops=getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        return ops.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS,android.os.Process.myUid(),packageName)==AppOpsManager.MODE_ALLOWED
    }
    private fun saveAndStart() {
        if(!consent.isChecked){status.text="Açık rıza olmadan izleme başlatılamaz.";return}
        if(!hasUsageAccess()){status.text="Önce Usage Access izni verin.";return}
        if(token.text.isBlank()){status.text="Backend erişim token'ı gerekli.";return}
        getSharedPreferences("ozhex",MODE_PRIVATE).edit().putString("api_url",api.text.toString().trim()).putString("access_token",token.text.toString().trim()).putBoolean("consent",true).apply()
        startForegroundService(Intent(this,UsageMonitorService::class.java))
        status.text="İzleme başladı. Kalıcı bildirim görünür."
    }
}
