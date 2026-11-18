# Linux Tutor laboratory shell integration.
# Records each interactive command (time, user, directory, exit status, text)
# so the tutor can recognise *how* an outcome was reached.  Marking is always
# based on the resulting system state, never on this log alone.
if [ -n "$BASH_VERSION" ] && [ -n "$PS1" ]; then
    __tutor_last_hist=""
    __tutor_log() {
        local status=$?
        local line num cmd
        line=$(HISTTIMEFORMAT= builtin history 1)
        num=${line%%[!0-9 ]*}; num=${num// /}
        if [ -n "$num" ] && [ "$num" != "$__tutor_last_hist" ]; then
            __tutor_last_hist=$num
            cmd=${line#*[0-9]  }
            cmd=${cmd//$'\t'/ }
            printf '%s\t%s\t%s\t%s\t%s\n' "$(date +%s)" "$USER" "$PWD" "$status" "$cmd" \
                >> /var/lib/tutor/cmdlog 2>/dev/null
        fi
        builtin history -a 2>/dev/null
        return $status
    }
    case ";${PROMPT_COMMAND};" in
        *";__tutor_log;"*) ;;
        *) PROMPT_COMMAND="__tutor_log${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;
    esac
    HISTSIZE=5000
    HISTFILESIZE=10000
    shopt -s histappend
fi

# Show the laboratory welcome banner once, in the first login shell of a session.
if [ -n "$PS1" ] && shopt -q login_shell 2>/dev/null && [ "${SHLVL:-1}" -le 1 ] && [ -z "$TUTOR_MOTD_SHOWN" ]; then
    export TUTOR_MOTD_SHOWN=1
    [ -r /etc/motd ] && cat /etc/motd
fi
