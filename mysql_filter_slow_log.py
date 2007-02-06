#!/usr/bin/env python
# -*- coding: iso-8859-15 -*-


# MySQL Log Filter 1.4
# =====================
#
# Copyright 2007 Ren� Leonhardt
#
# Website: http://code.google.com/p/mysql-log-filter/
#
# This program is free software you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
# ABOUT MySQL Log Filter
# =======================
# The MySQL Log Filter allows you to easily filter only useful information of the
# MySQL Slow Query Log.
#
#
# LICENSE
# =======
# This code is released under the GPL. The full code is available from the website
# listed above.


"""Parse the MySQL Slow Query Log from STDIN and write all filtered queries to STDOUT.

In order to activate it see http://dev.mysql.com/doc/refman/5.1/en/slow-query-log.html.
For example you could add the following lines to your my.ini or my.cnf configuration file under the [mysqld] section:

long_query_time=3
log-slow-queries
log-queries-not-using-indexes


Example input lines:

# Time: 070119 12:29:58
# User@Host: root[root] @ localhost []
# Query_time: 1  Lock_time: 0  Rows_sent: 1  Rows_examined: 12345
SELECT * FROM test;
"""

usage = """MySQL Slow Query Log Filter 1.4 for Python 2.5

Usage:
# Filter slow queries executed for at least 3 seconds not from root, remove duplicates,
# apply execution count as first sorting value and save first 10 unique queries to file
python mysql_filter_slow_log.py -T=3 -eu=root --no-duplicates --sort-execution-count --top=10 < linux-slow.log > mysql-slow-queries.log

# Start permanent filtering of all slow queries from now on: at least 3 seconds or examining 10000 rows, exclude users root and test
tail -f -n 0 linux-slow.log | python mysql_filter_slow_log.py -T=3 -R=10000 -eu=root -eu=test &
# (-n 0 outputs only lines generated after start of tail)

# Stop permanent filtering
kill `ps auxww | grep 'tail -f -n 0 linux-slow.log' | egrep -v grep | awk '{print $2}'`


Options:
-T=min_query_time    Include only queries which took at least min_query_time seconds [default: 1]
-R=min_rows_examined Include only queries which examined at least min_rows_examined rows

-iu=include_user  Include only queries which contain include_user in the user field [multiple]
-eu=exclude_user  Exclude all queries which contain exclude_user in the user field [multiple]
-iq=include_query Include only queries which contain the string include_query (i.e. database or table name) [multiple]

--no-duplicates Output only unique query strings with additional statistics:
                Execution count, first and last timestamp.
                Query time: avg / max / sum.
                Lock time: avg / max / sum.
                Rows examined: avg / max / sum.
                Rows sent: avg / max / sum.

Default ordering of unique queries:
--sort-sum-query-time    [ 1. position]
--sort-avg-query-time    [ 2. position]
--sort-max-query-time    [ 3. position]
--sort-sum-lock-time     [ 4. position]
--sort-avg-lock-time     [ 5. position]
--sort-max-lock-time     [ 6. position]
--sort-sum-rows-examined [ 7. position]
--sort-avg-rows-examined [ 8. position]
--sort-max-rows-examined [ 9. position]
--sort-execution-count   [10. position]
--sort-sum-rows-sent     [11. position]
--sort-avg-rows-sent     [12. position]
--sort-max-rows-sent     [13. position]

--top=max_unique_qery_count Output maximal max_unique_qery_count different unique qeries
--details                   Enables output of timestamp based unique query time lines after user list
                            (i.e. # Query_time: 81  Lock_time: 0  Rows_sent: 884  Rows_examined: 2448350).


--help Output this message only and quit

[multiple] options can be passed more than once to set multiple values.
[position] options take the position of their first occurence into account.
           The first passed option will replace the default first sorting, ...
           Remaining default ordering options will keep their relative positions.
"""

import locale
import os
import sys
import time


# http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52560
locale.setlocale(locale.LC_NUMERIC,
                 os.name == 'nt' and 'en' or 'en_US.ISO8859-1')
def array_unique(seq):
    """Return a unique list of the sequence elements."""

    d ={}
    return [d.setdefault(e,e) for e in seq if e not in d]


# http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/473872
def number_format(num, places=0):
    """Format a number with grouped thousands and given decimal places"""

    return locale.format("%.*f", (places, num), True)


def cmp_query_times(a, b):
    """Compare two query executions by Query_time, Lock_time, Rows_examined."""

    for i in (0,1,3):
        if a[i] != b[i]:
            return -1 * cmp(a[i], b[i])
    return 0

def cmp_queries(a, b):
    """Compare two queries by the ordering defined in new_sorting."""

    for i in new_sorting:
        if a[1][i] != b[1][i]:
            return -1 * cmp(a[1][i], b[1][i])
    return 0

def cmp_users(a, b):
    """Compare two users lexicographically."""

    return cmp(a[0], b[0])

def process_query(queries, query, no_duplicates, user, timestamp, query_time, ls):
    """Print or save query for later printing."""

    if no_duplicates:
        if not queries.has_key(query):
            queries[query] = {}
        if not queries[query].has_key(user):
            queries[query][user] = {timestamp: query_time}
        else:
            queries[query][user][timestamp] = query_time
    else:
        print '# Time: %s%s# User@Host: %s%s# Query_time: %d  Lock_time: %d  '\
              'Rows_sent: %d  Rows_examined: %d%s%s%s' % (timestamp, ls, user,
              ls, query_time[0], query_time[1], query_time[2], query_time[3],
              ls, query, ls),


min_query_time = 1
min_rows_examined = 0
include_users = []
exclude_users = []
include_queries = []
no_duplicates = False
details = False;
ls = os.linesep
default_sorting = [4, 'sum-query-time', 2, 'avg-query-time', 3, 'max-query-time', 7, 'sum-lock-time', 5, 'avg-lock-time', 6, 'max-lock-time', 13, 'sum-rows-examined', 11, 'avg-rows-examined', 12, 'max-rows-examined', 1, 'execution-count', 10, 'sum-rows-sent', 8, 'avg-rows-sent', 9, 'max-rows-sent'];
new_sorting = [];
top = 0;


# Decode all parameters to Unicode before parsing
fs_encoding = sys.getfilesystemencoding()
sys.argv = [s.decode(fs_encoding) for s in sys.argv]

# TODO: use optparse
for arg in sys.argv:
    _arg = arg[:3]
    try:
        if '-T=' == _arg: min_query_time = abs(int(arg[3:]))
        elif '-R=' == _arg: min_rows_examined = abs(int(arg[3:]))
        elif '-iu' == _arg: include_users.append(arg[4:])
        elif '-eu' == _arg: exclude_users.append(arg[4:])
        elif '-iq' == _arg: include_queries.append(arg[4:])
        elif '--no-duplicates' == arg: no_duplicates = True
        elif '--details' == arg: details = True
        elif '--sort-' == arg[:7]:
            sorting = arg[7:]
            if len(sorting) > 1 and sorting in default_sorting:
                i = default_sorting.index(sorting)-1
                if default_sorting[i] not in new_sorting:
                    new_sorting.append(default_sorting[i])
        elif '--top=' == arg[:6]:
            _top = abs(int(arg[6:]))
            if _top:
                top = _top;
        elif '--help' == arg:
            print >>sys.stderr, usage
            sys.exit()
    except ValueError, e:
        pass
include_users = array_unique(include_users)
exclude_users = array_unique(exclude_users)
for i in range(0, len(default_sorting)-1, 2):
    if default_sorting[i] not in new_sorting:
        new_sorting.append(default_sorting[i])


in_query = False
query = ''
timestamp = ''
user = ''
query_time = []
queries = {}

for line in sys.stdin:
    if not line: continue
    if line[0] == '#' and line[1] == ' ':
        if query:
            if include_queries:
                in_query = False
                for iq in include_queries:
                    if iq in query:
                        in_query = True
                        break
            if in_query:
                process_query(queries, query, no_duplicates, user, timestamp,
                    query_time, ls)
            query = ''
            in_query = False

        if line[2] == 'T':  # # Time: 070119 12:29:58
            timestamp = line[8:-1]
        elif line[2] == 'U': # # User@Host: root[root] @ localhost []
            user = line[13:-1]

            if not include_users:
                in_query = True
                for eu in exclude_users:
                    if eu in user:
                        in_query = False
                        break
            else:
                in_query = False
                for iu in include_users:
                    if iu in user:
                        in_query = True
                        break
        # # Query_time: 0  Lock_time: 0  Rows_sent: 0  Rows_examined: 156
        elif in_query and line[2] == 'Q':
            numbers = line[12:-1].split(':')
            query_time = (int(numbers[1].split()[0]), int(numbers[2].split()[0]),
                          int(numbers[3].split()[0]), int(numbers[4]))
            in_query = query_time[0] >= min_query_time or (min_rows_examined
                       and query_time[3] >= min_rows_examined)

    elif in_query:
        query += line[:-1]

if query:
    process_query(queries, query, no_duplicates, user, timestamp, query_time, ls)

if no_duplicates:
    lines = {}
    for query, users in queries.items():
        execution_count = 0
        max_timestamp = 0.0
        min_timestamp = 2147483647.0
        sum_query_time = max_query_time = 0
        sum_lock_time = max_lock_time = 0
        sum_rows_examined = max_rows_examined = 0
        sum_rows_sent = max_rows_sent = 0
        output = ''
        for user, timestamps in sorted(users.iteritems(), cmp_users):
            output += "# User@Host: %s%s" % (user, ls)
            query_times = {}
            for t, query_time in timestamps.iteritems():
                t = time.mktime(time.strptime(t, '%y%m%d %H:%M:%S'))
                if not query_times.has_key(query_time):
                    query_times[query_time] = "# Query_time: %d  Lock_time: "\
                        "%d  Rows_sent: %d  Rows_examined: %d%s" % (query_time[0],
                        query_time[1], query_time[2], query_time[3], ls)
                    if query_time[0] > max_query_time:
                        max_query_time = query_time[0]
                    if query_time[1] > max_lock_time:
                        max_lock_time = query_time[1]
                    if query_time[2] > max_rows_sent:
                        max_rows_sent = query_time[2]
                    if query_time[3] > max_rows_examined:
                        max_rows_examined = query_time[3]
                if t < min_timestamp:
                    min_timestamp = t
                elif t > max_timestamp:
                    max_timestamp = t
                sum_query_time += query_time[0]
                sum_lock_time += query_time[1]
                sum_rows_sent += query_time[2]
                sum_rows_examined += query_time[3]
                execution_count += 1
            if details:
                for query_time in sorted(query_times.iterkeys(), cmp_query_times):
                    output += query_times[query_time]
        output += "%s%s%s" % (ls, query, ls*2)
        avg_query_time = round(float(sum_query_time) / float(execution_count), 1)
        avg_lock_time = round(float(sum_lock_time) / float(execution_count), 1)
        avg_rows_sent = round(sum_rows_sent / execution_count, 0)
        avg_rows_examined = round(sum_rows_examined / execution_count, 0)
        lines[query] = [output, execution_count, avg_query_time, max_query_time,
                        sum_query_time, avg_lock_time, max_lock_time,
                        sum_lock_time, avg_rows_sent, max_rows_sent,
                        sum_rows_sent, avg_rows_examined, max_rows_examined,
                        sum_rows_examined, min_timestamp, max_timestamp]

    i = 0
    for query, data in sorted(lines.iteritems(), cmp_queries):
        # Determine maximum size for each column
        max_length = [3,3,3]
        for k in range(2, 14):
            c = k % 3;
            if c == 2:
                c = 0
            else:
                c += 1; # 2 -> 2 -> 0 | 3 -> 0 -> 1 | 4 -> 1 -> 2
            data[k] = number_format(data[k], not c and 1 or 0)
            if len(data[k]) > max_length[c]:
                max_length[c] = len(data[k])

        # Remove trailing 0 if all average values end with it
        k = True
        for c in [2,5,8,11]:
            if data[c][-1] != '0':
                k = False
                break
        if k:
            for c in [2,5,8,11]:
                data[c] = data[c][:-2]
            max_length[0] -= 2

        output, execution_count, avg_query_time, max_query_time,\
        sum_query_time, avg_lock_time, max_lock_time, sum_lock_time,\
        avg_rows_sent, max_rows_sent, sum_rows_sent, avg_rows_examined,\
        max_rows_examined, sum_rows_examined, min_timestamp, max_timestamp = data

        execution_count = number_format(data[1])
        print "# Execution count: %s time%s" % (execution_count, data[1] != 1 and 's' or ''),
        if max_timestamp:
          print "between %s and %s.%s" % (time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(min_timestamp)), time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(max_timestamp)), ls),
        else:
          print "on %s.%s" % (time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(min_timestamp)), ls),

        print "# Column       :", 'avg'.rjust(max_length[0]), "|", 'max'.rjust(max_length[1]), "| %s%s" % ('sum'.rjust(max_length[2]), ls),
        print "# Query time   :", avg_query_time.rjust(max_length[0]), "|", max_query_time.rjust(max_length[1]), "| %s%s" % (sum_query_time.rjust(max_length[2]), ls),
        print "# Lock time    :", avg_lock_time.rjust(max_length[0]), "|", max_lock_time.rjust(max_length[1]), "| %s%s" % (sum_lock_time.rjust(max_length[2]), ls),
        print "# Rows examined:", avg_rows_examined.rjust(max_length[0]), "|", max_rows_examined.rjust(max_length[1]), "| %s%s" % (sum_rows_examined.rjust(max_length[2]), ls),
        print "# Rows sent    :", avg_rows_sent.rjust(max_length[0]), "|", max_rows_sent.rjust(max_length[1]), "| %s%s" % (sum_rows_sent.rjust(max_length[2]), ls),
        print output,

        if top:
            i += 1
            if i >= top:
                break;
