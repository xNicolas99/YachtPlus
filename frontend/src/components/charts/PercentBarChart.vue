<template>
  <Bar :data="chartdata" :options="options" />
</template>

<script>
import { Bar } from "vue-chartjs";
import { Chart as ChartJS, Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale } from 'chart.js';

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale);

export default {
  name: 'PercentBarChart',
  components: { Bar },
  props: {
    chartdata: {
      type: Object,
      default: () => ({ labels: [], datasets: [] })
    }
  },
  data() {
    return {
      options: {
        responsive: true,
        animation: {
          duration: 0
        },
        scales: {
          y: {
             beginAtZero: true,
             min: 0,
             max: 100,
             ticks: {
               stepSize: 1,
               maxTicksLimit: 5
             }
          }
        }
      }
    };
  }
};
</script>
