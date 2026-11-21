/* SPDX-License-Identifier: GPL-2.0-or-later
 * Restore saved packages and remove newly introduced packages in one libalpm
 * transaction. No repositories, downloads, forced dependencies or overwrites.
 * The privileged Python helper supplies a root-owned, verified recovery plan.
 */
#include <alpm.h>
#include <json-c/json.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static json_object *field(json_object *object,const char *key,enum json_type type) {
    json_object *value=NULL;
    if(!json_object_object_get_ex(object,key,&value)||!json_object_is_type(value,type)) {
        fprintf(stderr,"Invalid recovery plan field: %s\n",key);exit(2);
    }
    return value;
}
static const char *string(json_object *object,const char *key) {
    return json_object_get_string(field(object,key,json_type_string));
}
static void validate(json_object *plan) {
    /* Validate the complete document before taking libalpm's lock. A malformed
     * retained record must not leave db.lck behind or fail after a commit. */
    const char *strings[]={"root","database","gpgdir","logfile"};
    for(size_t i=0;i<sizeof(strings)/sizeof(*strings);++i) {
        if(string(plan,strings[i])[0]!='/') {
            fprintf(stderr,"Recovery path must be absolute: %s\n",strings[i]);exit(2);
        }
    }
    field(plan,"database_only",json_type_boolean);
    const char *lists[]={"architectures","hookdirs","noupgrade","noextract"};
    for(size_t i=0;i<sizeof(lists)/sizeof(*lists);++i) {
        json_object *list=field(plan,lists[i],json_type_array);
        for(size_t j=0;j<json_object_array_length(list);++j)
            if(!json_object_is_type(json_object_array_get_idx(list,j),json_type_string))exit(2);
    }
    json_object *inventory=field(plan,"inventory",json_type_object);
    json_object_object_foreach(inventory,name,version) {
        if(!*name||!json_object_is_type(version,json_type_string)||!*json_object_get_string(version))exit(2);
    }
    const char *operations[]={"add","remove"};
    for(size_t i=0;i<2;++i) {
        json_object *list=field(plan,operations[i],json_type_array);
        for(size_t j=0;j<json_object_array_length(list);++j) {
            json_object *item=json_object_array_get_idx(list,j);
            if(!*string(item,"name")||!*string(item,"version"))exit(2);
            if(i==0&&string(item,"path")[0]!='/')exit(2);
        }
    }
    json_object *reasons=field(plan,"reasons",json_type_object);
    json_object_object_foreach(reasons,package,reason) {
        if(!*package||!json_object_is_type(reason,json_type_int)||json_object_get_int(reason)<0||json_object_get_int(reason)>1)exit(2);
    }
}
static void logging(void *context,alpm_loglevel_t level,const char *format,va_list args) {
    (void)context;
    if(level&(ALPM_LOG_ERROR|ALPM_LOG_WARNING))vfprintf(stderr,format,args);
}
static void question(void *context,alpm_question_t *query) {
    (void)context;
    /* Every addition/removal is already explicit. Reject unexpected changes,
     * skipping unresolved targets, importing keys and deleting bad archives. */
    query->any.answer=0;
}
static void event(void *context,alpm_event_t *value) {
    (void)context;
    if(value->type==ALPM_EVENT_SCRIPTLET_INFO)fputs(value->scriptlet_info.line,stdout);
    if(value->type==ALPM_EVENT_PACKAGE_OPERATION_DONE) {
        alpm_pkg_t *package=value->package_operation.newpkg;
        printf("%s %s\n",package?"Restored":"Removed new package",
               alpm_pkg_get_name(package?package:value->package_operation.oldpkg));
        fflush(stdout);
    }
}
static void errors(alpm_handle_t *handle,alpm_list_t *details) {
    alpm_errno_t code=alpm_errno(handle);
    fprintf(stderr,"Package recovery failed: %s\n",alpm_strerror(code));
    for(alpm_list_t *item=details;item;item=item->next) {
        if(code==ALPM_ERR_UNSATISFIED_DEPS) {
            alpm_depmissing_t *missing=item->data;
            char *dependency=alpm_dep_compute_string(missing->depend);
            fprintf(stderr,"%s requires %s\n",missing->target,dependency);
            free(dependency);alpm_depmissing_free(missing);
        }else if(code==ALPM_ERR_CONFLICTING_DEPS) {
            alpm_conflict_t *conflict=item->data;
            fprintf(stderr,"Conflicting packages: %s and %s\n",
                alpm_pkg_get_name(conflict->package1),alpm_pkg_get_name(conflict->package2));
            alpm_conflict_free(conflict);
        }else if(code==ALPM_ERR_FILE_CONFLICTS) {
            alpm_fileconflict_t *conflict=item->data;
            fprintf(stderr,"File conflict: %s (%s)\n",conflict->file,conflict->target);
            alpm_fileconflict_free(conflict);
        }
    }
    alpm_list_free(details);
}
static int options(alpm_handle_t *handle,json_object *plan,const char *key,
                   int (*add)(alpm_handle_t *,const char *)) {
    json_object *values=field(plan,key,json_type_array);
    for(size_t i=0;i<json_object_array_length(values);++i) {
        json_object *value=json_object_array_get_idx(values,i);
        if(!json_object_is_type(value,json_type_string)||add(handle,json_object_get_string(value))<0)return -1;
    }
    return 0;
}
int main(int argc,char **argv) {
    if(argc!=2){fputs("Expected a recovery plan pathname.\n",stderr);return 2;}
    json_object *plan=json_object_from_file(argv[1]);
    if(!plan||!json_object_is_type(plan,json_type_object)){fputs("Invalid recovery plan.\n",stderr);return 2;}
    validate(plan);
    const char *root=string(plan,"root"),*database=string(plan,"database");
    int dbonly=json_object_get_boolean(field(plan,"database_only",json_type_boolean));
    if(root[0]!='/'||database[0]!='/'||(!strcmp(root,"/")&&(dbonly||geteuid()!=0))) {
        fputs("Live package changes require administrator access; database rehearsals need a private root.\n",stderr);return 2;
    }
    alpm_errno_t code=0;
    alpm_handle_t *handle=alpm_initialize(root,database,&code);
    if(!handle){fprintf(stderr,"Cannot open package database: %s\n",alpm_strerror(code));return 1;}
    int result=1,initialized=0;
    alpm_list_t *details=NULL;
    alpm_option_set_logcb(handle,logging,NULL);
    alpm_option_set_eventcb(handle,event,NULL);
    alpm_option_set_questioncb(handle,question,NULL);
    if(alpm_option_set_gpgdir(handle,string(plan,"gpgdir"))<0||
       alpm_option_set_logfile(handle,string(plan,"logfile"))<0||
       alpm_option_set_checkspace(handle,!dbonly)<0||
       options(handle,plan,"architectures",alpm_option_add_architecture)<0||
       options(handle,plan,"hookdirs",alpm_option_add_hookdir)<0||
       options(handle,plan,"noupgrade",alpm_option_add_noupgrade)<0||
       options(handle,plan,"noextract",alpm_option_add_noextract)<0)goto failure;
    int flags=ALPM_TRANS_FLAG_NEEDED;
    if(dbonly)flags|=ALPM_TRANS_FLAG_DBONLY|ALPM_TRANS_FLAG_NOSCRIPTLET|ALPM_TRANS_FLAG_NOHOOKS;
    if(alpm_trans_init(handle,flags)<0)goto failure;
    initialized=1;
    /* Check the whole installed inventory while holding libalpm's lock. */
    json_object *inventory=field(plan,"inventory",json_type_object);
    alpm_db_t *local=alpm_get_localdb(handle);
    alpm_list_t *installed=alpm_db_get_pkgcache(local);
    if(alpm_list_count(installed)!=(size_t)json_object_object_length(inventory)) {
        fputs("Installed packages changed before recovery acquired the package lock.\n",stderr);goto done;
    }
    json_object_object_foreach(inventory,name,version) {
        alpm_pkg_t *package=alpm_db_get_pkg(local,name);
        if(!json_object_is_type(version,json_type_string)||!package||
           strcmp(alpm_pkg_get_version(package),json_object_get_string(version))) {
            fprintf(stderr,"Package changed before recovery: %s\n",name);goto done;
        }
    }
    json_object *remove=field(plan,"remove",json_type_array);
    for(size_t i=0;i<json_object_array_length(remove);++i) {
        json_object *item=json_object_array_get_idx(remove,i);
        const char *name=string(item,"name"),*version=string(item,"version");
        alpm_pkg_t *package=alpm_db_get_pkg(local,name);
        if(!package||strcmp(alpm_pkg_get_version(package),version)) {
            fprintf(stderr,"Removal version changed: %s\n",name);goto done;
        }
        if(alpm_remove_pkg(handle,package)<0)goto failure;
    }
    json_object *add=field(plan,"add",json_type_array);
    for(size_t i=0;i<json_object_array_length(add);++i) {
        json_object *item=json_object_array_get_idx(add,i);
        alpm_pkg_t *package=NULL;
        /* Required trusted signatures: no OPTIONAL or TRUST_UNKNOWN flags. */
        if(alpm_pkg_load(handle,string(item,"path"),1,ALPM_SIG_PACKAGE,&package)<0)goto failure;
        if(strcmp(alpm_pkg_get_name(package),string(item,"name"))||
           strcmp(alpm_pkg_get_version(package),string(item,"version"))) {
            fprintf(stderr,"Recovery archive identity differs: %s\n",string(item,"path"));
            alpm_pkg_free(package);goto done;
        }
        if(alpm_add_pkg(handle,package)<0){alpm_pkg_free(package);goto failure;}
    }
    if(alpm_trans_prepare(handle,&details)<0)goto failure;
    if(alpm_trans_commit(handle,&details)<0)goto failure;
    json_object *reasons=field(plan,"reasons",json_type_object);
    json_object_object_foreach(reasons,package_name,reason) {
        alpm_pkg_t *package=alpm_db_get_pkg(local,package_name);
        int value=json_object_get_int(reason);
        if(!package||!json_object_is_type(reason,json_type_int)||value<0||value>1||
           alpm_pkg_set_reason(package,value)<0)goto failure;
    }
    result=0;goto done;
failure:
    errors(handle,details);
done:
    if(initialized)alpm_trans_release(handle);
    alpm_release(handle);json_object_put(plan);
    return result;
}
