#!/bin/bash

##################################################################
#
# Runs a suite of MiniNDN experiments and moves
# the resulting # log files to a specific output directory.
#
# Andre Dexheimer Carneiro      06/12/2021
#
#################################################################

# Default values
n_iterations=3
flag_run_icn=0
flag_run_ip=0
flag_run_sdn=0
flag_run_ip_sdn=0
flag_save_nfd_log=0
output_dir=""
topology_path=""
log_path="runSuite.log"
username="vagrant"

show_help () {

    echo -e "\n  runSuite: runs benchmark suite for ICN networks"
    echo "  Usage:
      ./runSuite -t <topology_path> <options> -o <output_path>
      The options are:
      -h: Show this
      -n: Overrides the number of iterations for each benchmark (default $n_iterations)

      By default, all three benchmarks are run. When any of the following parameters are passed, the behavior changes so that only those specified are run.
      --icn: Pure ICN benchmark
      --sdn: ICN + SDN benchmark
      --ip: IP benchmark
      --ip_sdn: IP with SDN benchmark

      -o: Output path for the resulting MiniNDN logs
      -t: Topology file
      "
}

run_benchmark () {
    # $1 -> experiment type (sdn, icn, ip, ip_sdn)
    # $2 -> experiment iteration
    echo "Running $1 experiment iteration $2" >> $log_path
    sudo ./experiment_send.py -t $topology_path --$1
    mkdir -p $output_dir/$1/run$2
    for host_dir in $(ls /tmp/minindn)
    do
        mkdir $output_dir/$1/run$2/$host_dir
        sudo mv /tmp/minindn/$host_dir/consumerLog.log $output_dir/$1/run$2/$host_dir
        if [ "$flag_save_nfd_log" = 1 ]; then
            sudo mv /tmp/minindn/$host_dir/log $output_dir/$1/run$2/$host_dir
        fi
        sudo chmod -R 755 $output_dir/$1/run$2/$host_dir
    done

    cp ../log/experiment_send.log $output_dir/$1/run$2
    sudo rm ../log/experiment_send.log
    sudo chown -R $username $output_dir
}

echo "Starting time=$(date)" >> $log_path

# Read commmand line parameters
while getopts "h?n:?icn-:?sdn-:?ip-:?o:t:sdn-:?" opt; do
    case "$opt" in
    h|\?)
        show_help
        exit 0
        ;;
    n)
        n_iterations=$OPTARG
        echo "Number of iterations=$n_iterations"
        ;;
    o)
        output_dir=$OPTARG
        echo "Output path=$output_dir"
        ;;
    t)
        topology_path=$OPTARG
        ;;
    -)
        case "${OPTARG}" in
            sdn)
                flag_run_sdn=1
                echo "SDN"
                ;;
            icn)
                flag_run_icn=1
                echo "ICN"
                ;;
            ip)
                flag_run_ip=1
                echo "IP"
                ;;
            id_sdn)
                flag_run_ip_sdn=1
                echo "IP with SDN"
                ;;
            *)
                echo "Unknown argument --${OPTARG}"
                ;;
        esac;;
    esac
done

# Decide which benchmarks to run
if [ "$flag_run_sdn" = 0 ] && [ "$flag_run_icn" = 0 ] && [ "$flag_run_ip" = 0 ] && [ "$flag_run_ip_sdn" = 0 ]; then
    # If the benchmarks have not been specified, run all
    flag_run_sdn=1
    flag_run_icn=1
    flag_run_ip=1
    flag_run_ip_sdn=1
fi

# Check output directory
if [ "$output_dir" != "" ]
then
    if [ ! -d "$output_dir" ]
    then
        mkdir $output_dir
    fi
else
    echo "ERROR: No output directory specified"
    show_help
    exit 0
fi

echo "About to run experiments with iterations=$n_iterations" >> $log_path
# Run experiments
for i in $(seq 1 $n_iterations)
do
    # SDN benchmark
    if [ "$flag_run_sdn" = 1 ]
    then
        run_benchmark "sdn" "$i"
    fi
    # ICN benchmark
    if [ "$flag_run_icn" = 1 ]
    then
        run_benchmark "icn" "$i"
    fi
    # IP benchmark
    if [ "$flag_run_ip" = 1 ]
    then
        run_benchmark "ip" "$i"
    fi
    # IP with SDN benchmark
    if [ "$flag_run_ip_sdn" = 1 ]
    then
        run_benchmark "ip_sdn" "$i"
    fi
done

echo "Done!" >> $log_path
