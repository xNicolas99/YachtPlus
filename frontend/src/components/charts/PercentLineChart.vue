<template>
  <LineChart :data="chartdata" :options="options" />
</template>

<script>
import { Line } from "vue-chartjs";
import { Chart as ChartJS, Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale, TimeScale } from 'chart.js';
import 'chartjs-adapter-date-fns';

ChartJS.register(Title, Tooltip, Legend, LineElement, PointElement, CategoryScale, LinearScale, TimeScale);

export default {
  name: 'PercentLineChart',
  components: { LineChart: Line },
  props: {
    chartdata: {
      type: Object,
      default: () => ({ labels: [], datasets: [] })
    }
  },
  data() {
    return {
      options: {
        animation: {
          duration: 0
        },
        plugins: {
          tooltip: {
            mode: "index",
            intersect: false,
            callbacks: {
              label: function(context) {
                return context.parsed.y + "%";
              }
            }
          },
          legend: {
            display: true
          }
        },
        hover: {
          mode: "index",
          intersect: true
        },
        scales: {
          y: {
            beginAtZero: true,
            min: 0,
            max: 100,
            ticks: {
              stepSize: 1,
              maxTicksLimit: 10
            },
            grid: {
              display: true
            }
          },
          x: {
            type: "time",
            time: {
              unit: "second",
              displayFormats: {
                second: "h:mm:ss a"
              }
            },
            ticks: {
              autoSkip: true,
              autoSkipPadding: 15,
              maxRotation: 0,
              maxTicksLimit: 5
            },
            grid: {
              display: false
            }
          }
        },
        responsive: true,
        maintainAspectRatio: false
      }
    };
  }
};
</script>
