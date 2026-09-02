package com.mediaview.player

import android.app.Activity
import android.app.role.RoleManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings

object KioskSetup {
    fun isDefaultHome(context: Context): Boolean {
        val home = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME)
        return context.packageManager.resolveActivity(home, 0)?.activityInfo?.packageName == context.packageName
    }

    fun requestHomeRole(activity: Activity) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roles = activity.getSystemService(RoleManager::class.java)
            if (roles?.isRoleAvailable(RoleManager.ROLE_HOME) == true && !roles.isRoleHeld(RoleManager.ROLE_HOME)) {
                activity.startActivity(roles.createRequestRoleIntent(RoleManager.ROLE_HOME))
                return
            }
        }
        runCatching { activity.startActivity(Intent(Settings.ACTION_HOME_SETTINGS)) }
            .onFailure {
                activity.startActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME))
            }
    }
}