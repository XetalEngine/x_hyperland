-- Xetal's editors own the .conf settings. Read them on each compositor reload
-- and use the native Lua API on Hyprland 0.57+. No startup actions run at render.
local root = debug.getinfo(1, "S").source:sub(2):match("^(.*)/[^/]+$")
local function quote(value) return "'" .. value:gsub("'", "'\\''") .. "'" end
local pipe = assert(io.popen("/usr/bin/python3 " .. quote(root .. "/compat/hypr_compat.py") .. " render " .. quote(root) .. " 2>&1", "r"))
local source = pipe:read("*a")
-- Hyprland reaps child processes itself; pclose can report ECHILD even after
-- success. The reader emits this marker only after the entire render succeeds.
pipe:close()
local marker = "-- Xetal settings rendered successfully\n"
assert(source:sub(1, #marker) == marker, "Could not read Xetal settings:\n" .. source:sub(1, 3000))
local config = assert(load(source, "@" .. root .. "/hyprland.conf (generated Lua)"))
-- Generated exec commands give only our apps the IPC adapter environment.
-- Do not change the compositor PATH, which upstream may export over D-Bus.
config()
