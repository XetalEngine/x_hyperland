/* Waybar 0.15 CFFI ABI v2. See the upstream API:
 * https://github.com/Alexays/Waybar/blob/0.15.0/resources/custom_modules/cffi_example/waybar_cffi_module.h
 */
#pragma once
#include <gtk/gtk.h>
typedef struct wbcffi_module wbcffi_module;
typedef struct {
    wbcffi_module *obj;
    const char *waybar_version;
    GtkContainer *(*get_root_widget)(wbcffi_module *);
    void (*queue_update)(wbcffi_module *);
} wbcffi_init_info;
typedef struct { const char *key; const char *value; } wbcffi_config_entry;
