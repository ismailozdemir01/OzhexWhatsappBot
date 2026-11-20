package com.ozhex.whatsapp

import android.app.*
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.IBinder
import okhttp3.*
import org.json.JSONObject
import java.time.Instant
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class UsageMonitorService:Service() {
    private val executor=Executors.newSingleThreadScheduledExecutor()
    private val client=OkHttpClient.Builder().callTimeout(12,TimeUnit.SECONDS).build()
    private var last:Boolean?=null
    private val prefs by lazy { getSharedPreferences("ozhex",Context.MODE_PRIVATE) }
    override fun onCreate(){
        super.onCreate()
        val channel="ozhex_usage"
        if(android.os.Build.VERSION.SDK_INT>=26) getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel(channel,"Ozhex activity sharing",NotificationManager.IMPORTANCE_LOW))
        val n=if(android.os.Build.VERSION.SDK_INT>=26) Notification.Builder(this,channel) else Notification.Builder(this)
        startForeground(17,n.setContentTitle("Ozhex activity sharing active").setContentText("Only this device's WhatsApp app usage is monitored.").setSmallIcon(android.R.drawable.ic_menu_view).build())
        executor.scheduleWithFixedDelay({ pollUsage() },0,5,TimeUnit.SECONDS)
    }
    private fun pollUsage(){
        if(!prefs.getBoolean("consent",false)){stopSelf();return}
        try{
            val manager=getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
            val stream=manager.queryEvents(System.currentTimeMillis()-12000,System.currentTimeMillis())
            val event=android.app.usage.UsageEvents.Event()
            var current:Boolean?=null
            while(stream.hasNextEvent()){
                stream.getNextEvent(event)
                if(event.packageName=="com.whatsapp"){
                    if(event.eventType==android.app.usage.UsageEvents.Event.MOVE_TO_FOREGROUND) current=true
                    if(event.eventType==android.app.usage.UsageEvents.Event.MOVE_TO_BACKGROUND) current=false
                }
            }
            if(current!=null && current!=last){send(current!!);last=current}
        }catch(_:Exception){}
    }
    private fun send(foreground:Boolean){
        val base=(prefs.getString("api_url","")?: "").trimEnd('/')
        val auth=prefs.getString("access_token","")?:return
        if(base.isBlank()||auth.isBlank())return
        val key=prefs.getString("device_key",null)?:UUID.randomUUID().toString().also{prefs.edit().putString("device_key",it).apply()}
        val media="application/json; charset=utf-8".toMediaType()
        fun post(path:String,body:JSONObject):Boolean{
            val req=Request.Builder().url(base+path).header("Authorization","Bearer "+auth).post(body.toString().toRequestBody(media)).build()
            return try{client.newCall(req).execute().use{it.isSuccessful}}catch(_:Exception){false}
        }
        if(!post("/api/v1/devices",JSONObject().put("device_key",key).put("platform","android").put("label",android.os.Build.MODEL)))return
        post("/api/v1/activity",JSONObject().put("device_key",key).put("event_type",if(foreground)"foreground" else "background").put("occurred_at",Instant.now().toString()))
    }
    override fun onDestroy(){executor.shutdownNow();super.onDestroy()}
    override fun onBind(intent:Intent?):IBinder?=null
}
