<template>
  <div class="chart-container">
    <Bar :data="chartData" :options="mergedOptions" />
  </div>
</template>

<script>
import { Bar } from 'vue-chartjs'
import { Chart as ChartJS, Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale } from 'chart.js'

ChartJS.register(Title, Tooltip, Legend, BarElement, CategoryScale, LinearScale)

export default {
  name: 'PercentBarChart',
  components: { Bar },
  props: {
    chartData: {
      type: Object,
      required: true
    },
    chartOptions: {
      type: Object,
      default: () => ({})
    }
  },
  computed: {
    mergedOptions() {
      const defaultOptions = {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            min: 0,
            max: 100
          }
        },
        plugins: {
          legend: {
            display: false
          }
        }
      };
      return { ...defaultOptions, ...this.chartOptions };
    }
  }
}
</script>

<style scoped>
.chart-container {
  position: relative;
  height: 200px; /* Default height */
}
</style>
